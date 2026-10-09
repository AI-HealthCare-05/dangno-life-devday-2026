"""Restore verified short Today explanations in the isolated local database.

Dry-run by default. --apply backs up SQLite first; predictions and inputs stay intact.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({k: v for k, v in dotenv_values(ROOT / ".env.local-mobile").items() if v is not None})


def main():
    # Import configuration only after the local environment has been loaded.
    from app.services.ai_jobs import _release_demo_explanation

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    database = ROOT / "storage/local_mobile.sqlite3"
    con = sqlite3.connect(f"{database.as_uri()}?mode={'rw' if args.apply else 'ro'}", uri=True)
    try:
        rows = con.execute("""
            SELECT p.id, p.job_id, j.result FROM predictions p
            JOIN prediction_jobs j ON p.job_id=j.job_id
            WHERE p.model_key='diabetes_current_screening'
              AND p.result_status='approved' AND p.display_allowed=1
              AND p.operational_model_activated=1 AND p.explanation_status='research_only'
              AND NOT EXISTS(SELECT 1 FROM risk_factors f WHERE f.prediction_id=p.id)
        """).fetchall()
        repairs = []
        for prediction_id, job_id, raw in rows:
            result = json.loads(raw or "{}")
            explanation = result.get("explanation") or {}
            if explanation.get("selection_status") != "insufficient_directional_factors":
                continue
            released = _release_demo_explanation(explanation, operational=True)
            if (
                released["display_allowed"]
                and all(
                    {"feature", "display_name", "direction", "contribution", "message"} <= item.keys()
                    for item in released["items"]
                )
                and released.get("explanation_version")
            ):
                result["explanation"] = released
                repairs.append((prediction_id, job_id, result))
        print(f"Verified local Today explanations eligible for repair: {len(repairs)}")
        if not args.apply or not repairs:
            return
        backup = ROOT / "outputs/mobile" / f"xai-backup-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.sqlite3"
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as snapshot:
            con.backup(snapshot)
        with con:
            for prediction_id, job_id, result in repairs:
                explanation = result["explanation"]
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
                con.execute("UPDATE predictions SET explanation_status='approved' WHERE id=?", (prediction_id,))
                con.execute(
                    "UPDATE prediction_jobs SET result=? WHERE job_id=?",
                    (json.dumps(result, ensure_ascii=False), job_id),
                )
        print(
            f"Repaired {len(repairs)} explanations; original predictions and inputs preserved. Backup saved under outputs/mobile."
        )
    finally:
        con.close()


if __name__ == "__main__":
    main()
