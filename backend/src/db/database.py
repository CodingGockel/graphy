from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.db.models import Base

# Arbitrary constant key for the transaction-level advisory lock that serializes
# schema creation across worker processes (see init_db).
_SCHEMA_INIT_LOCK_KEY = 0x5746_5031  # "SWEP1"


async def init_db(database_url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # With multiple uvicorn workers, each process runs create_all on startup.
        # create_all's "check then CREATE" is not atomic across connections, so two
        # workers can race and one hits a duplicate-key error on the pg_type catalog.
        # A transaction-scoped advisory lock serializes them: the first creates the
        # tables, the rest find them already present. The lock auto-releases on commit.
        await conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SCHEMA_INIT_LOCK_KEY})
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    return engine, sessionmaker
