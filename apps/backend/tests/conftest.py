import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_ENV = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "PUBLIC_BASE_URL": "https://testserver",
    "WEB_INTERNAL_API_URL": "http://test-api",
    "SESSION_SECRET": "test-session-secret-at-least-32-bytes",
    "CSRF_SECRET": "test-csrf-secret-at-least-32-bytes-now",
    "GOOGLE_CLIENT_ID": "test-google-client-id",
    "GOOGLE_CLIENT_SECRET": "test-google-client-secret",
    "OTARI_BASE_URL": "https://otari.invalid",
    "OTARI_AI_TOKEN": "test-otari-token",
    "OTARI_MAIN_MODEL": "competitor-scout-main",
    "OTARI_CHILD_MODEL": "competitor-scout-child",
}

os.environ.update(TEST_ENV)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
POSTGRES_ADMIN_DSN = os.environ.get(
    "TEST_POSTGRES_ADMIN_DSN",
    "postgresql://competitor_scout:competitor_scout@localhost:5432/postgres",
)
POSTGRES_DATABASE_PREFIX = "competitor_scout_test_"


async def _create_database(database_name: str) -> None:
    connection = await asyncpg.connect(POSTGRES_ADMIN_DSN)
    try:
        await connection.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await connection.close()


async def _drop_database(database_name: str) -> None:
    connection = await asyncpg.connect(POSTGRES_ADMIN_DSN)
    try:
        await connection.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            database_name,
        )
        await connection.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    database_name = f"{POSTGRES_DATABASE_PREFIX}{uuid.uuid4().hex}"
    database_url = (
        f"postgresql+asyncpg://competitor_scout:competitor_scout@localhost:5432/{database_name}"
    )
    asyncio.run(_create_database(database_name))

    alembic_config = Config(BACKEND_ROOT / "alembic.ini")
    alembic_config.attributes["database_url"] = database_url
    command.upgrade(alembic_config, "head")

    try:
        yield database_url
    finally:
        asyncio.run(_drop_database(database_name))


@pytest_asyncio.fixture
async def db_session(migrated_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    async with session_factory() as session:
        yield session

    if transaction.is_active:
        await transaction.rollback()
    await connection.close()
    await engine.dispose()
