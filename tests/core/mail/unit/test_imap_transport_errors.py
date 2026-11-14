"""Unit: текст ошибки IMAP/SMTP-транспорта при голом TimeoutError."""

from __future__ import annotations

import pytest

from core.mail.exceptions import MailTransportError
from core.mail.models import MailboxSecret
from core.mail.transport.imap_smtp import ImapSmtpTransport, _io_error_detail


def test_io_error_detail_names_empty_timeout() -> None:
    assert _io_error_detail(TimeoutError()) == "timeout"
    assert _io_error_detail(OSError()) == "OSError"
    assert _io_error_detail(OSError("connection refused")) == "connection refused"


@pytest.mark.asyncio
async def test_login_imap_timeout_error_message_is_not_empty() -> None:
    class _TimeoutClient:
        async def login(self, _user: str, _password: str) -> None:
            raise TimeoutError

    transport = ImapSmtpTransport(
        imap_host="imap.example.com",
        imap_port=993,
        smtp_host="smtp.example.com",
        smtp_port=465,
    )

    async def _fake_connect(*, timeout: float = 30.0) -> _TimeoutClient:
        return _TimeoutClient()

    transport._connect_imap = _fake_connect  # type: ignore[method-assign]

    with pytest.raises(MailTransportError, match=r"IMAP login failed for user@example\.com: timeout"):
        _ = await transport._login_imap(
            MailboxSecret(email_address="user@example.com", password="x")
        )
