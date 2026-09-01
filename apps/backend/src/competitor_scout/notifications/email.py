from __future__ import annotations

from html import escape
from typing import Protocol
from urllib.parse import urljoin

import httpx


class EmailDeliveryError(RuntimeError):
    code = "email_delivery_failed"

    def __init__(self, *, retryable: bool = True) -> None:
        super().__init__("email provider request failed")
        self.retryable = retryable


class EmailSender(Protocol):
    async def send(
        self,
        *,
        recipient: str,
        subject: str,
        text: str,
        html: str,
        idempotency_key: str,
    ) -> None: ...


class ResendEmailSender:
    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._client = client or httpx.AsyncClient(
            base_url="https://api.resend.com",
            timeout=15.0,
        )
        self._owns_client = client is None

    async def send(
        self,
        *,
        recipient: str,
        subject: str,
        text: str,
        html: str,
        idempotency_key: str,
    ) -> None:
        try:
            response = await self._client.post(
                "/emails",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Idempotency-Key": idempotency_key,
                },
                json={
                    "from": self._sender,
                    "to": [recipient],
                    "subject": subject,
                    "text": text,
                    "html": html,
                },
            )
        except httpx.HTTPError as error:
            raise EmailDeliveryError() from error
        if response.is_error:
            raise EmailDeliveryError(
                retryable=response.status_code == 429 or response.status_code >= 500
            )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class DisabledEmailSender:
    async def send(self, **_kwargs: str) -> None:
        raise EmailDeliveryError(retryable=False)

    async def aclose(self) -> None:
        return None


def render_notification_email(
    notification_type: str,
    payload: dict[str, object],
    *,
    public_base_url: str,
) -> tuple[str, str, str]:
    if notification_type == "finding_email":
        title = _required_text(payload, "title")
        summary = _required_text(payload, "summary")
        competitor = _required_text(payload, "competitor_name")
        level = _required_text(payload, "significance_level").capitalize()
        link = _app_link(public_base_url, "findings", _required_text(payload, "finding_id"))
        subject = f"{level} competitor change: {title}"
        text = f"{competitor}\n\n{title}\n{summary}\n\nView finding: {link}"
        html = (
            f"<p>{escape(competitor)}</p><h1>{escape(title)}</h1>"
            f'<p>{escape(summary)}</p><p><a href="{escape(link, quote=True)}">'
            "View finding</a></p>"
        )
        return subject, text, html
    if notification_type == "weekly_brief_email":
        title = _required_text(payload, "title")
        summary = _required_text(payload, "executive_summary")
        link = _app_link(public_base_url, "briefs", _required_text(payload, "brief_id"))
        subject = title
        text = f"{title}\n\n{summary}\n\nView brief: {link}"
        html = (
            f"<h1>{escape(title)}</h1><p>{escape(summary)}</p>"
            f'<p><a href="{escape(link, quote=True)}">View brief</a></p>'
        )
        return subject, text, html
    raise ValueError("unsupported notification type")


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"notification payload is missing {key}")
    return value


def _app_link(public_base_url: str, resource: str, record_id: str) -> str:
    base = public_base_url.rstrip("/") + "/"
    return urljoin(base, f"{resource}/{record_id}")
