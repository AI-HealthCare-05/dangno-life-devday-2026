"""Migration checks use an isolated database and contain no actual health records."""
import importlib
from types import SimpleNamespace

import pytest
from tortoise import Tortoise

MIGRATION = importlib.import_module("app.core.db.migrations.models.28_20261016090000_editable_diagnosis_records")


@pytest.mark.asyncio
async def test_diagnosis_schema_is_repeatable_and_rollback_preserves_history():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["aerich.models"]})
    db = Tortoise.get_connection("default")
    try:
        await db.execute_script(await MIGRATION.upgrade(db))
        await db.execute_script("""
            INSERT INTO health_diagnosis_records
            (id,user_id,record_date,eligibility_check_ids,is_active,created_at,updated_at)
            VALUES (1,999,'2026-10-01','[]',1,'2026-10-01','2026-10-01');
        """)
        await db.execute_script(await MIGRATION.upgrade(db))
        await db.execute_script(await MIGRATION.downgrade(db))
        rows = await db.execute_query_dict("SELECT id,is_active FROM health_diagnosis_records")
        assert rows == [{"id": 1, "is_active": 1}]
        columns = await db.execute_query_dict("PRAGMA table_info(health_diagnosis_records)")
        assert {"source_checkup_id", "eligibility_check_ids", "deleted_at"} <= {row["name"] for row in columns}
    finally:
        await Tortoise.close_connections()


@pytest.mark.asyncio
async def test_mysql_migration_uses_auto_increment_and_unique_user_day():
    sql = await MIGRATION.upgrade(SimpleNamespace(capabilities=SimpleNamespace(dialect="mysql")))
    assert "BIGINT PRIMARY KEY AUTO_INCREMENT" in sql
    assert "UNIQUE (user_id, record_date)" in sql
    assert "eligibility_check_ids JSON NOT NULL" in sql
