"""Recompute local Today explanations only; preserve predictions and inputs.

Dry-run by default. --apply creates a private SQLite backup before atomic writes.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({k: v for k, v in dotenv_values(ROOT / ".env.local-mobile").items() if v is not None})


def main():
    # Import configuration only after the local environment has been loaded.
    from app.core import config
    from app.services.ai_jobs import _release_demo_explanation
    from app.services.health import HealthService
    from src.ml.inference.diabetes_current_screening import load_current_screening_model, predict_artifact
    from src.ml.inference.xai_background import explain_today_with_reference, load_today_background

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    loaded = load_current_screening_model(
        manifest_path=Path(config.CURRENT_SCREENING_MANIFEST_URI), model_path=config.CURRENT_SCREENING_MODEL_URI
    )
    _, reference = load_today_background(loaded.manifest["model_version"], loaded.manifest["artifact_sha256"])
    con = sqlite3.connect(
        f"{(ROOT / 'storage/local_mobile.sqlite3').as_uri()}?mode={'rw' if args.apply else 'ro'}", uri=True
    )
    con.row_factory = sqlite3.Row
    try:
        predictions = con.execute("""SELECT p.*,j.request_payload,j.result FROM predictions p
            JOIN prediction_jobs j ON p.job_id=j.job_id
            WHERE p.model_key='diabetes_current_screening' AND p.result_status='approved'
              AND p.display_allowed=1 AND p.operational_model_activated=1""").fetchall()
        repairs = []
        for prediction in predictions:
            result = json.loads(prediction["result"] or "{}")
            if (result.get("explanation") or {}).get("reference_sha256") == reference["artifact_sha256"]:
                continue
            if (
                prediction["model_version"] != loaded.manifest["model_version"]
                or prediction["model_artifact_digest"] != loaded.manifest["artifact_sha256"]
            ):
                continue
            params = json.loads(prediction["request_payload"])
            checkup = con.execute(
                "SELECT * FROM health_checkups WHERE id=? AND user_id=?",
                (prediction["health_checkup_id"], prediction["user_id"]),
            ).fetchone()
            screening = con.execute(
                "SELECT * FROM current_screening_inputs WHERE id=? AND user_id=?",
                (params.get("current_screening_input_id"), prediction["user_id"]),
            ).fetchone()
            if checkup is None or screening is None:
                continue
            payload = HealthService.current_screening_payload(
                SimpleNamespace(**dict(checkup)), SimpleNamespace(**dict(screening))
            )
            frame = pd.DataFrame([{name: payload[name] for name in loaded.manifest["features"]}])
            score_batch = partial(predict_artifact, loaded.artifact)
            score = float(score_batch(frame)[0])
            if not np.isclose(score, prediction["internal_score"], atol=1e-8, rtol=0):
                raise ValueError("Saved inputs no longer reproduce the frozen prediction; no database changes made")
            explanation = explain_today_with_reference(
                frame,
                score_batch,
                model_version=loaded.manifest["model_version"],
                model_digest=loaded.manifest["artifact_sha256"],
                elevated=prediction["risk_category"] == "high",
            )
            explanation = _release_demo_explanation(explanation, operational=True)
            if not explanation["display_allowed"] or not explanation["additivity_verified"]:
                raise ValueError("New explanation failed its release checks; no database changes made")
            result["explanation"] = explanation
            repairs.append((prediction["id"], prediction["job_id"], result))
        print(f"Verified Today explanations ready for the Train reference: {len(repairs)}")
        if not args.apply or not repairs:
            return
        backup = ROOT / "outputs/mobile" / f"xai-reference-backup-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.sqlite3"
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as snapshot:
            con.backup(snapshot)
        with con:
            for prediction_id, job_id, result in repairs:
                explanation = result["explanation"]
                con.execute("DELETE FROM risk_factors WHERE prediction_id=?", (prediction_id,))
                for order, item in enumerate(explanation["items"], 1):
                    con.execute(
                        """INSERT INTO risk_factors
                        (prediction_id,factor_name,display_name,impact_direction,importance_score,
                         display_order,is_modifiable,message,explanation_version,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (
                            prediction_id,
                            item["feature"],
                            item["display_name"],
                            item["direction"],
                            abs(item["contribution"]),
                            order,
                            item.get("modifiable") is True,
                            item["message"],
                            explanation["explanation_version"],
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                con.execute(
                    "UPDATE prediction_jobs SET result=? WHERE job_id=?",
                    (json.dumps(result, ensure_ascii=False), job_id),
                )
                con.execute("UPDATE predictions SET explanation_status='approved' WHERE id=?", (prediction_id,))
        print(
            f"Applied {len(repairs)} explanations; prediction scores, thresholds and all health inputs unchanged. Private backup saved."
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
