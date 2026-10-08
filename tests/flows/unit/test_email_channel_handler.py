"""Unit tests for EmailChannelHandler (mailbox + SMTP delivery)."""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from unittest.mock import patch

import aiosmtplib
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


class _SmtpCapture:
    def __init__(self) -> None:
        self.username: str = ""
        self.password: str = ""
        self.data: str = ""
        self.port: int = 0


async def _start_smtp_capture() -> tuple[asyncio.Server, _SmtpCapture]:
    capture = _SmtpCapture()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"220 localhost ready\r\n")
        await writer.drain()
        while True:
            line = await reader.readline()
            if not line:
                break
            command = line.decode().strip()
            upper = command.upper()
            if upper.startswith("EHLO") or upper.startswith("HELO"):
                writer.write(b"250-localhost\r\n250 AUTH PLAIN\r\n")
            elif upper.startswith("AUTH PLAIN"):
                payload = command.split(" ", 2)
                blob = payload[2] if len(payload) == 3 else ""
                if blob == "":
                    writer.write(b"334\r\n")
                    await writer.drain()
                    blob = (await reader.readline()).decode().strip()
                decoded = base64.b64decode(blob).decode()
                _prefix, username, password = decoded.split("\0", 2)
                capture.username = username
                capture.password = password
                writer.write(b"235 ok\r\n")
            elif upper.startswith("MAIL FROM") or upper.startswith("RCPT TO") or upper.startswith("RSET"):
                writer.write(b"250 ok\r\n")
            elif upper == "DATA":
                writer.write(b"354 end with dot\r\n")
                await writer.drain()
                chunks: list[bytes] = []
                while True:
                    data_line = await reader.readline()
                    if data_line in {b".\r\n", b".\n", b""}:
                        break
                    chunks.append(data_line)
                capture.data = b"".join(chunks).decode()
                writer.write(b"250 queued\r\n")
            elif upper.startswith("QUIT"):
                writer.write(b"221 bye\r\n")
                await writer.drain()
                break
            else:
                writer.write(b"250 ok\r\n")
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    sockets = server.sockets
    if sockets is None or not sockets:
        raise RuntimeError("SMTP capture server has no socket")
    capture.port = int(sockets[0].getsockname()[1])
    return server, capture


@pytest.mark.asyncio
async def test_send_smtp_message_uses_aiosmtplib() -> None:
    server, capture = await _start_smtp_capture()
    try:
        result = await send_smtp_message(
            smtp_host="127.0.0.1",
            smtp_port=capture.port,
            smtp_user="me@example.com",
            password="secret",
            from_email="me@example.com",
            to_addresses=["a@example.com"],
            subject="Hi",
            body_text="Hello",
            body_html=None,
            in_reply_to=None,
            references=None,
            use_tls=False,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert capture.username == "me@example.com"
    assert capture.password == "secret"
    assert "Subject: Hi" in capture.data
    assert "Hello" in capture.data
    assert result["accepted"] == ["a@example.com"]
    message_id = result["message_id"]
    assert isinstance(message_id, str)
    assert "@" in message_id


@pytest.mark.asyncio
async def test_send_smtp_message_returns_accepted_when_quit_fails() -> None:
    class _QuitFails:
        def __init__(self, **_kwargs: object) -> None:
            return None

        async def connect(self) -> str:
            return "220"

        async def login(self, user: str, password: str) -> str:
            _ = user, password
            return "235"

        async def send_message(self, message: object) -> tuple[dict[str, str], str]:
            _ = message
            return {}, "250"

        async def quit(self) -> str:
            raise aiosmtplib.SMTPException("421 closing")

    with patch("apps.flows.src.channels.email.aiosmtplib.SMTP", _QuitFails):
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
    assert result["accepted"] == ["a@example.com"]


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
