"""Unit: IMAP FLAGS → unread, newest-first ordering helpers."""

from __future__ import annotations

from core.mail.transport.imap_smtp import (
    _BODY_FETCH,
    _extract_message_flags_from_fetch,
    _parse_message_flags_blob,
)


def test_body_fetch_uses_peek_so_list_does_not_mark_seen() -> None:
    assert "BODY.PEEK[]" in _BODY_FETCH
    assert "RFC822" not in _BODY_FETCH


def test_parse_message_flags_blob_seen() -> None:
    assert _parse_message_flags_blob(r"\Seen \Recent").unread is False
    assert _parse_message_flags_blob(r"\Answered \Seen").unread is False


def test_parse_message_flags_blob_unseen() -> None:
    assert _parse_message_flags_blob(r"\Recent").unread is True
    assert _parse_message_flags_blob("").unread is True
    assert _parse_message_flags_blob(r"\Flagged").unread is True


def test_extract_message_flags_from_fetch_lines() -> None:
    seen_lines = [b"* 1 FETCH (UID 42 FLAGS (\\Seen) BODY[] {0})"]
    assert _extract_message_flags_from_fetch(seen_lines).unread is False
    unseen_lines = [b"* 2 FETCH (UID 43 FLAGS (\\Recent) RFC822 {10})"]
    assert _extract_message_flags_from_fetch(unseen_lines).unread is True
    missing_flags = [b"* 3 FETCH (UID 44 RFC822 {10})"]
    assert _extract_message_flags_from_fetch(missing_flags).unread is True
