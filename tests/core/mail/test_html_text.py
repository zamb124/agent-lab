"""HTML → видимый текст для snippet/RAG."""

from __future__ import annotations

from datetime import datetime, timezone

from core.mail.html_text import html_to_visible_text, looks_like_html, mail_snippet
from core.mail.models import InboundMailMessage, StoredMailMessage
from core.mail.service import stored_to_list_item, to_message_list_item


def test_html_to_visible_text_strips_tags_and_script() -> None:
    html = (
        "<html><head><style>.x{color:red}</style><script>alert(1)</script></head>"
        "<body><p>Hello <b>world</b></p></body></html>"
    )
    assert html_to_visible_text(html) == "Hello world"


def test_looks_like_html_detects_doctype_and_html() -> None:
    assert looks_like_html("<!DOCTYPE html><html></html>") is True
    assert looks_like_html("<html xmlns:v='urn:schemas-microsoft-com:vml'>") is True
    assert looks_like_html("Just a plain sentence") is False


def test_mail_snippet_from_html_when_no_plain() -> None:
    snippet = mail_snippet(body_text=None, body_html="<p>Hello from bank</p>")
    assert snippet == "Hello from bank"


def test_mail_snippet_prefers_plain_over_html() -> None:
    snippet = mail_snippet(
        body_text="plain body",
        body_html="<p>html body</p>",
    )
    assert snippet == "plain body"


def test_mail_snippet_strips_legacy_html_copied_into_body_text() -> None:
    html = "<html><body>old receipt</body></html>"
    snippet = mail_snippet(body_text=html, body_html=html)
    assert "<html" not in snippet
    assert "old receipt" in snippet


def test_to_message_list_item_snippet_from_html() -> None:
    item = to_message_list_item(
        InboundMailMessage(uid="1", body_html="<p>Hello from bank</p>"),
    )
    assert item.snippet == "Hello from bank"


def test_stored_to_list_item_strips_legacy_html_snippet() -> None:
    now = datetime.now(timezone.utc)
    stored = StoredMailMessage(
        mail_message_id="m1",
        company_id="c1",
        mailbox_binding_id="b1",
        folder="INBOX",
        uid=1,
        thread_id="t1",
        snippet="<html><body>old receipt</body></html>",
        synced_at=now,
        created_at=now,
        updated_at=now,
    )
    item = stored_to_list_item(stored)
    assert item.snippet is not None
    assert "<html" not in item.snippet
    assert "old receipt" in item.snippet
