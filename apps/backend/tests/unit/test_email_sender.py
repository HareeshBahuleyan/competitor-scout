import json
import uuid

import httpx
import pytest

from competitor_scout.notifications.email import (
    EmailDeliveryError,
    ResendEmailSender,
    render_notification_email,
)


async def test_resend_sender_uses_server_credentials_and_provider_idempotency() -> None:
    captured: dict[str, object] = {}

    async def transport(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["idempotency"] = request.headers["Idempotency-Key"]
        captured["json"] = json.loads(request.content)
        return httpx.Response(202, json={"id": "provider-message"})

    client = httpx.AsyncClient(
        base_url="https://api.resend.com", transport=httpx.MockTransport(transport)
    )
    sender = ResendEmailSender(
        api_key="server-only-key", sender="Scout <scout@example.com>", client=client
    )
    await sender.send(
        recipient="owner@example.com",
        subject="Pricing changed",
        text="Plain body",
        html="<p>HTML body</p>",
        idempotency_key="email:finding:opaque-id",
    )

    assert captured == {
        "authorization": "Bearer server-only-key",
        "idempotency": "email:finding:opaque-id",
        "json": {
            "from": "Scout <scout@example.com>",
            "to": ["owner@example.com"],
            "subject": "Pricing changed",
            "text": "Plain body",
            "html": "<p>HTML body</p>",
        },
    }
    await client.aclose()


async def test_provider_errors_do_not_expose_auth_or_response_body() -> None:
    async def transport(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="private provider diagnostic")

    client = httpx.AsyncClient(
        base_url="https://api.resend.com", transport=httpx.MockTransport(transport)
    )
    sender = ResendEmailSender(api_key="private-key", sender="scout@example.com", client=client)
    with pytest.raises(EmailDeliveryError) as captured:
        await sender.send(
            recipient="owner@example.com",
            subject="Subject",
            text="Text",
            html="<p>HTML</p>",
            idempotency_key="stable-key",
        )
    rendered = repr(captured.value)
    assert "private-key" not in rendered
    assert "private provider diagnostic" not in rendered
    await client.aclose()


def test_email_rendering_escapes_dynamic_html_and_uses_same_origin_links() -> None:
    finding_id = uuid.uuid4()
    subject, text, html = render_notification_email(
        "finding_email",
        {
            "finding_id": str(finding_id),
            "competitor_name": "Acme <script>",
            "title": "Pricing & packaging",
            "summary": "A <b>new</b> tier.",
            "significance_level": "high",
        },
        public_base_url="https://scout.example",
    )
    assert subject == "High competitor change: Pricing & packaging"
    assert f"https://scout.example/findings/{finding_id}" in text
    assert "<script>" not in html
    assert "<b>new</b>" not in html
