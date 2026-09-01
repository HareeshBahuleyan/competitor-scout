import uuid

from competitor_scout.services.notifications import brief_email_key, finding_email_key


def test_notification_deduplication_keys_are_opaque_and_stable() -> None:
    finding_id = uuid.uuid4()
    brief_id = uuid.uuid4()
    assert finding_email_key(finding_id) == f"email:finding:{finding_id}"
    assert brief_email_key(brief_id) == f"email:brief:{brief_id}"
