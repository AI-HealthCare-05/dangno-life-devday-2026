"""Run trusted CV artifacts against repository demo images, without user data."""

import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


async def main():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local-mobile")
    # This smoke check always stays local, irrespective of server VLM settings.
    os.environ["OPENAI_VLM_FALLBACK_ENABLED"] = "false"
    os.environ["OPENAI_API_KEY"] = ""
    from app.vision.food_vision import food_vision_is_configured, get_food_vision_provider

    assert food_vision_is_configured(), "CV artifact hashes/settings are not ready"
    provider = get_food_vision_provider()
    results = []
    for name in ("vegetable-meal-1.png", "vegetable-meal-low-veg.png", "irrelevant-desk.png"):
        photo = ROOT / "src/frontend/assets/demo" / name
        result = await provider.analyze(photo.read_bytes(), "image/png", name)
        assert result.provider_kind == "local_kfood_cv"
        assert result.decision_status in {"valid", "invalid_food_ratio", "invalid_vegetable_ratio", "uncertain"}
        assert 0 <= result.food_coverage_percent <= 100
        assert 0 <= result.vegetable_ratio_percent <= 100
        expected = {
            "vegetable-meal-1.png": "valid",
            "vegetable-meal-low-veg.png": "invalid_vegetable_ratio",
            "irrelevant-desk.png": "invalid_food_ratio",
        }
        assert result.decision_status == expected[name], f"Unexpected decision for {name}"
        results.append({"image": name, **asdict(result)})
        print(f"OK {name}: provider={result.provider_kind}, decision={result.decision_status}")
    (ROOT / "outputs/cv-smoke.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
