"""Import existing diagnosis answers after the schema migration; print no user data."""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def backfill() -> None:
    from tortoise import Tortoise

    from app.core.db.databases import TORTOISE_ORM
    from app.services.health_diagnosis import backfill_legacy_diagnoses

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await backfill_legacy_diagnoses()
        print("Diagnosis history backfill completed.")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Run after database backup and migration 28.")
    args = parser.parse_args()
    if not args.apply:
        parser.exit(message="No data changed. Apply migration 28, then rerun with --apply.\n")
    asyncio.run(backfill())
