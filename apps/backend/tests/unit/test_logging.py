from competitor_scout.logging import redact_sensitive


def test_sensitive_log_values_are_redacted_recursively() -> None:
    event = {
        "event": "agent request completed",
        "authorization": "Bearer secret",
        "context": {
            "prompt": "private prompt",
            "items": [{"quoted_evidence": "private page content"}],
            "run_id": "safe-run-id",
        },
    }

    redacted = redact_sensitive(None, "info", event)

    assert redacted == {
        "event": "agent request completed",
        "authorization": "[REDACTED]",
        "context": {
            "prompt": "[REDACTED]",
            "items": [{"quoted_evidence": "[REDACTED]"}],
            "run_id": "safe-run-id",
        },
    }
