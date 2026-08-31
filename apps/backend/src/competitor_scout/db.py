from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from competitor_scout.config import Settings


class Base(DeclarativeBase):
    pass


SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_dependency(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: SessionFactory | None = request.app.state.session_factory
    if session_factory is None:
        raise RuntimeError("database session factory is not configured")
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def check_database_readiness(session_factory: SessionFactory) -> None:
    async with session_factory() as session:
        await session.execute(text("SELECT 1"))
