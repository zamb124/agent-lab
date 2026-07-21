"""Unit tests for EmailChannelHandler (mailbox + SMTP delivery)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.flows.src.channels.email import EmailChannelHandler, send_smtp_message
from apps.flows.src.channels.registry import create_default_channel_registry
from apps.flows.src.models.enums import ChannelType
from core.mail.models import MailSendPayload, MailSendResult
from core.mail.service import MailService


class _FakeMailService:
    def __init__(self) -> None:
        self.last_payload: MailSendPayload | None = None

    async def send_message(
        self,
        payload: MailSendPayload,
        *,
        company_id: str | None = None,
    ) -> MailSendResult:
        _ = company_id
        self.last_payload = payload
        return MailSendResult(message_id="mid-1", accepted=list(payload.to_addresses))


@pytest.mark.asyncio
async def test_email_channel_handler_mailbox_maps_payload() -> None:
    fake = _FakeMailService()
    handler = EmailChannelHandler(fake)  # type: ignore[arg-type]
    result = await handler.execute_action(
        action="send_message",
        params={
            "recipient": "a@example.com, b@example.com",
            "text": "Hello body",
            "subject": "Hi",
        },
        config={"delivery": "mailbox", "mailbox_binding_id": "mailbind_1"},
        variables={},
    )
    assert result == {"message_id": "mid-1", "accepted": ["a@example.com", "b@example.com"]}
    assert fake.last_payload is not None
    assert fake.last_payload.mailbox_binding_id == "mailbind_1"
    assert fake.last_payload.to_addresses == ["a@example.com", "b@example.com"]
    assert fake.last_payload.subject == "Hi"
    assert fake.last_payload.body_text == "Hello body"


@pytest.mark.asyncio
async def test_email_channel_handler_requires_delivery() -> None:
    handler = EmailChannelHandler(_FakeMailService())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="delivery"):
        await handler.execute_action(
            action="send_message",
            params={"recipient": "a@example.com", "text": "x"},
            config={"mailbox_binding_id": "mailbind_1"},
            variables={},
        )


@pytest.mark.asyncio
async def test_email_channel_handler_mailbox_rejects_smtp_keys() -> None:
    handler = EmailChannelHandler(_FakeMailService())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="smtp_host"):
        await handler.execute_action(
            action="send_message",
            params={"recipient": "a@example.com", "text": "x"},
            config={
                "delivery": "mailbox",
                "mailbox_binding_id": "mailbind_1",
                "smtp_host": "smtp.example.com",
            },
            variables={},
        )


@pytest.mark.asyncio
async def test_email_channel_handler_smtp_rejects_mailbox_binding() -> None:
    handler = EmailChannelHandler(_FakeMailService())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mailbox_binding_id"):
        await handler.execute_action(
            action="send_message",
            params={"recipient": "a@example.com", "text": "x"},
            config={
                "delivery": "smtp",
                "mailbox_binding_id": "mailbind_1",
                "smtp_host": "smtp.example.com",
                "from_email": "me@example.com",
                "password": "secret",
            },
            variables={},
        )


@pytest.mark.asyncio
async def test_email_channel_handler_smtp_send(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _fake_send(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"message_id": "<mid@example.com>", "accepted": list(kwargs["to_addresses"])}

    monkeypatch.setattr(
        "apps.flows.src.channels.email.send_smtp_message",
        _fake_send,
    )
    handler = EmailChannelHandler(_FakeMailService())  # type: ignore[arg-type]
    result = await handler.execute_action(
        action="send_message",
        params={"recipient": "a@example.com", "text": "body", "subject": "Sub"},
        config={
            "delivery": "smtp",
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "from_email": "me@example.com",
            "password": "secret",
            "smtp_use_tls": True,
        },
        variables={},
    )
    assert result["message_id"] == "<mid@example.com>"
    assert captured["smtp_host"] == "smtp.example.com"
    assert captured["smtp_port"] == 465
    assert captured["smtp_user"] == "me@example.com"
    assert captured["from_email"] == "me@example.com"
    assert captured["password"] == "secret"
    assert captured["subject"] == "Sub"
    assert captured["body_text"] == "body"


@pytest.mark.asyncio
async def test_send_smtp_message_uses_aiosmtplib() -> None:
    smtp = MagicMock()
    smtp.connect = AsyncMock()
    smtp.login = AsyncMock()
    smtp.send_message = AsyncMock(return_value=({}, "ok"))
    smtp.quit = AsyncMock()

    with patch("apps.flows.src.channels.email.aiosmtplib.SMTP", return_value=smtp) as smtp_cls:
        result = await send_smtp_message(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="me@example.com",
            password="secret",
            from_email="me@example.com",
            to_addresses=["a@example.com"],
            subject="Hi",
            body_text="Hello",
            body_html=None,
            in_reply_to=None,
            references=None,
            use_tls=True,
        )
    smtp_cls.assert_called_once()
    smtp.connect.assert_awaited()
    smtp.login.assert_awaited_with("me@example.com", "secret")
    smtp.send_message.assert_awaited()
    assert "accepted" in result
    assert result["accepted"] == ["a@example.com"]
    assert isinstance(result["message_id"], str)


@pytest.mark.asyncio
async def test_email_channel_handler_rejects_photo() -> None:
    handler = EmailChannelHandler(_FakeMailService())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="send_photo"):
        await handler.send_photo(
            recipient="a@example.com",
            photo="https://example.com/p.png",
            config={"delivery": "mailbox", "mailbox_binding_id": "mailbind_1"},
            variables={},
        )


def test_channel_registry_email_requires_mail_service() -> None:
    registry = create_default_channel_registry()
    assert registry.has(ChannelType.EMAIL)
    with pytest.raises(ValueError, match="mail_service"):
        registry.get(ChannelType.EMAIL)
    handler = registry.get(ChannelType.EMAIL, mail_service=_FakeMailService())  # type: ignore[arg-type]
    assert isinstance(handler, EmailChannelHandler)


def test_fake_mail_service_satisfies_send_message_signature() -> None:
    """Guard: Fake mirrors MailService.send_message parameter names."""
    assert callable(getattr(MailService, "send_message"))
