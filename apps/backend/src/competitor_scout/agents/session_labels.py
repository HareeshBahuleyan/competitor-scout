import uuid


def scout_run_session_label(run_id: uuid.UUID) -> str:
    """Group every Otari request for one Scout Run under one cost-attribution label."""
    return f"scout-run:{run_id}"
