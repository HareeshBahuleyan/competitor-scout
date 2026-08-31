from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from competitor_scout.models.auth import OAuthIdentity, Session, User


async def test_auth_records_persist_with_relationships(db_session) -> None:
    user = User(email=" Founder@Example.COM ", display_name="Founder", timezone="Europe/Berlin")
    identity = OAuthIdentity(provider="google", provider_subject="google-subject", user=user)
    session = Session(
        secret_hash="hashed-session-secret",
        expires_at=datetime.now(UTC) + timedelta(days=30),
        user=user,
    )
    db_session.add_all([user, identity, session])
    await db_session.commit()

    db_session.expunge_all()
    stored = await db_session.scalar(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.oauth_identities), selectinload(User.sessions))
    )
    assert stored is not None
    assert stored.email == "founder@example.com"
    assert stored.created_at.tzinfo is not None
    assert [item.provider_subject for item in stored.oauth_identities] == ["google-subject"]
    assert [item.secret_hash for item in stored.sessions] == ["hashed-session-secret"]


async def test_normalized_user_email_is_unique(db_session) -> None:
    db_session.add(User(email="Founder@Example.COM", display_name="Founder"))
    await db_session.commit()
    db_session.add(User(email=" founder@example.com ", display_name="Duplicate"))

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_provider_subject_is_unique_within_provider(db_session) -> None:
    first_user = User(email="first@example.com", display_name="First")
    second_user = User(email="second@example.com", display_name="Second")
    db_session.add_all(
        [
            OAuthIdentity(provider="google", provider_subject="shared-subject", user=first_user),
            OAuthIdentity(provider="google", provider_subject="shared-subject", user=second_user),
        ]
    )

    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_same_subject_is_allowed_for_different_providers(db_session) -> None:
    first_user = User(email="google@example.com", display_name="Google")
    second_user = User(email="other@example.com", display_name="Other")
    db_session.add_all(
        [
            OAuthIdentity(provider="google", provider_subject="shared-subject", user=first_user),
            OAuthIdentity(
                provider="test-provider",
                provider_subject="shared-subject",
                user=second_user,
            ),
        ]
    )
    await db_session.commit()

    count = await db_session.scalar(select(func.count()).select_from(OAuthIdentity))
    assert count == 2


async def test_session_can_be_revoked(db_session) -> None:
    user = User(email="founder@example.com", display_name="Founder", timezone="UTC")
    session = Session(
        user=user,
        secret_hash="hash",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add(session)
    await db_session.commit()

    session.revoked_at = datetime.now(UTC)
    await db_session.commit()

    stored = await db_session.scalar(select(Session).where(Session.id == session.id))
    assert stored is not None
    assert stored.revoked_at is not None
    assert stored.revoked_at.tzinfo is not None


async def test_deleting_user_cascades_identities_and_sessions(db_session) -> None:
    user = User(email="founder@example.com", display_name="Founder")
    identity = OAuthIdentity(provider="google", provider_subject="subject", user=user)
    session = Session(
        user=user,
        secret_hash="hash",
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    db_session.add_all([identity, session])
    await db_session.commit()
    identity_id = identity.id
    session_id = session.id
    db_session.expunge_all()
    stored_user = await db_session.get(User, user.id)
    assert stored_user is not None
    await db_session.delete(stored_user)
    await db_session.commit()

    assert await db_session.get(OAuthIdentity, identity_id) is None
    assert await db_session.get(Session, session_id) is None
