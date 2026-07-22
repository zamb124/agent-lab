"""Shared IMAP poll helpers for live mail suites."""

from __future__ import annotations

import asyncio

from core.mail.models import InboundMailMessage, MailboxSecret, MailFetchQuery
from core.mail.ports import MailServerPort


async def poll_fetch_message(
    port: MailServerPort,
    secret: MailboxSecret,
    *,
    message_id: str,
    subject: str,
    deadline_sec: float = 90.0,
    mailbox: str = "INBOX",
) -> InboundMailMessage | None:
    """Shared hosting может переписать Message-Id — матчим subject (+ id если сохранился)."""
    deadline = asyncio.get_running_loop().time() + deadline_sec
    while asyncio.get_running_loop().time() < deadline:
        messages = await port.fetch_messages(
            secret,
            MailFetchQuery(mailbox=mailbox, subject_contains=subject, limit=50),
        )
        for item in messages:
            if item.subject == subject:
                return item
            if item.message_id == message_id:
                return item
        all_recent = await port.fetch_messages(
            secret,
            MailFetchQuery(mailbox=mailbox, limit=50),
        )
        for item in all_recent:
            if item.subject == subject or item.message_id == message_id:
                return item
        await asyncio.sleep(2.0)
    return None
