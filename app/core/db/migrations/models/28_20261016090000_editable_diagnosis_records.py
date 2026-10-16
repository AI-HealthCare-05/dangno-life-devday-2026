from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient | None) -> str:
    if db is None:
        return "SELECT 1;"
    dialect = db.capabilities.dialect
    primary = "INTEGER PRIMARY KEY AUTOINCREMENT" if dialect == "sqlite" else "BIGINT PRIMARY KEY AUTO_INCREMENT"
    return f"""
        CREATE TABLE IF NOT EXISTS health_diagnosis_records (
            id {primary}, user_id BIGINT NOT NULL, record_date DATE NOT NULL,
            source_checkup_id BIGINT NULL, eligibility_check_id BIGINT NULL,
            eligibility_check_ids JSON NOT NULL, is_active BOOL NOT NULL DEFAULT 1,
            deleted_at TIMESTAMP NULL, created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL, UNIQUE (user_id, record_date)
        );
    """


async def downgrade(db: BaseDBAsyncClient | None) -> str:
    # Do not discard patient-entered history on rollback.
    return "SELECT 1;"
