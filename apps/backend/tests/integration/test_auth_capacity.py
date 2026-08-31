import asyncio

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.models.auth import User
from competitor_scout.services.auth import (
    GoogleIdentity,
    UserCapacityReached,
    upsert_google_user,
)


def identity(index: int) -> GoogleIdentity:
    return GoogleIdentity(
        subject=f"capacity-subject-{index}",
        email=f"capacity-{index}@example.com",
        display_name=f"Capacity User {index}",
        avatar_url=None,
        nonce=None,
    )


async def test_concurrent_google_signups_cannot_exceed_capacity(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def register(index: int) -> str:
        async with sessions() as session:
            try:
                user = await upsert_google_user(
                    session,
                    identity(index),
                    max_active_users=1,
                )
                await session.commit()
                return user.email
            except UserCapacityReached:
                await session.rollback()
                return "capacity-reached"

    try:
        async with sessions.begin() as session:
            await session.execute(delete(User))

        results = await asyncio.gather(register(1), register(2))

        assert sorted(results).count("capacity-reached") == 1
        async with sessions() as session:
            active_users = await session.scalar(
                select(func.count(User.id)).where(User.disabled_at.is_(None))
            )
        assert active_users == 1
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(User))
        await engine.dispose()
