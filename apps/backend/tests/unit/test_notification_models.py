import uuid

from competitor_scout.models.notifications import NotificationOutbox, NotificationStatus


def test_notification_outbox_has_safe_idempotent_persistence_contract() -> None:
    columns = NotificationOutbox.__table__.columns
    assert NotificationStatus.PENDING.value == "pending"
    assert NotificationStatus.SENT.value == "sent"
    assert NotificationStatus.FAILED.value == "failed"
    assert columns["user_id"].nullable is False
    assert columns["payload"].nullable is False
    assert columns["deduplication_key"].nullable is False
    assert columns["attempt_count"].nullable is False
    assert {index.name for index in NotificationOutbox.__table__.indexes} >= {
        "ix_notification_outbox_deduplication_key",
        "ix_notification_outbox_claimable",
    }
    assert {"api_key", "authorization", "credential", "secret"}.isdisjoint(columns.keys())

    row = NotificationOutbox(
        user_id=uuid.uuid4(),
        notification_type="finding_email",
        deduplication_key=f"email:finding:{uuid.uuid4()}",
        payload={"finding_id": str(uuid.uuid4()), "title": "Pricing changed"},
    )
    assert row.status in (None, NotificationStatus.PENDING)
