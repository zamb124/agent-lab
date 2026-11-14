"""Unit: текст ошибки IMAP/SMTP-транспорта при голом TimeoutError."""

from __future__ import annotations

import pytest

from core.mail.exceptions import MailTransportError
from core.mail.models import MailboxSecret
from core.mail.transport.imap_smtp import ImapSmtpTransport


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (TimeoutError(), r"IMAP login failed for user@example\.com: timeout"),
        (OSError(), r"IMAP login failed for user@example\.com: OSError"),
        (OSError("connection refused"), r"connection refused"),
    ],
)
async def test_check_imap_login_error_message_is_not_empty(
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
    expected: str,
) -> None:
    class _FailingClient:
        async def login(self, _user: str, _password: str) -> None:
            raise raised

    async def _fake_connect(*, timeout: float = 30.0) -> _FailingClient:
        _ = timeout
        return _FailingClient()

    transport = ImapSmtpTransport(
        imap_host="imap.example.com",
        imap_port=993,
        smtp_host="smtp.example.com",
        smtp_port=465,
    )
    monkeypatch.setattr(transport, "_connect_imap", _fake_connect)

    with pytest.raises(MailTransportError, match=expected):
        await transport.check_imap_login(
            MailboxSecret(email_address="user@example.com", password="x")
        )
