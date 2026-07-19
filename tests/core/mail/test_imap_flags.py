"""Unit: IMAP FLAGS → unread, newest-first ordering helpers."""

from __future__ import annotations

from core.mail.transport.imap_smtp import (
    _BODY_FETCH,
    _extract_unread_from_fetch,
    _flags_indicate_unread,
)


def test_body_fetch_uses_peek_so_list_does_not_mark_seen() -> None:
    assert "BODY.PEEK[]" in _BODY_FETCH
    assert "RFC822" not in _BODY_FETCH


def test_flags_indicate_unread_seen() -> None:
    assert _flags_indicate_unread(r"\Seen \Recent") is False
    assert _flags_indicate_unread(r"\Answered \Seen") is False


def test_flags_indicate_unread_unseen() -> None:
    assert _flags_indicate_unread(r"\Recent") is True
    assert _flags_indicate_unread("") is True
    assert _flags_indicate_unread(r"\Flagged") is True


def test_extract_unread_from_fetch_lines() -> None:
    seen_lines: list[object] = [b"* 1 FETCH (UID 42 FLAGS (\\Seen) BODY[] {0})"]
    assert _extract_unread_from_fetch(seen_lines) is False
    unseen_lines: list[object] = [b"* 2 FETCH (UID 43 FLAGS (\\Recent) RFC822 {10})"]
    assert _extract_unread_from_fetch(unseen_lines) is True
    missing_flags: list[object] = [b"* 3 FETCH (UID 44 RFC822 {10})"]
    assert _extract_unread_from_fetch(missing_flags) is True
