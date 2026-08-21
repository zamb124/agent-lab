"""Надёжный MIME: письмо всегда собирается, битый attach — stub."""

from __future__ import annotations

from email.message import EmailMessage

from core.mail.mime_parse import parse_inbound_rfc822, strip_attachment_payloads


def _build_multipart_with_attachment(*, attach_payload: bytes) -> bytes:
    root = EmailMessage()
    root["From"] = "sender@example.com"
    root["To"] = "recv@example.com"
    root["Subject"] = "with-attach"
    root["Message-ID"] = "<mime-parse-test@example.com>"
    root.set_content("plain body")
    root.add_attachment(
        attach_payload,
        maintype="application",
        subtype="octet-stream",
        filename="report.bin",
    )
    return root.as_bytes()


def test_parse_inbound_keeps_message_with_valid_attachment() -> None:
    raw = _build_multipart_with_attachment(attach_payload=b"hello-attach")
    message = parse_inbound_rfc822("42", raw)
    assert message.uid == "42"
    assert message.subject == "with-attach"
    assert message.body_text is not None
    assert "plain body" in message.body_text
    assert len(message.attachments) == 1
    assert message.attachments[0].filename == "report.bin"
    assert message.attachments[0].available is True
    assert message.attachments[0].content == b"hello-attach"


def test_parse_inbound_survives_completely_garbage_bytes() -> None:
    message = parse_inbound_rfc822("7", b"\xff\xfe\x00 not-a-mail \x80\x81")
    assert message.uid == "7"
    assert isinstance(message.attachments, list)


def test_parse_inbound_stub_attachment_on_empty_payload() -> None:
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    root = MIMEMultipart()
    root["From"] = "a@example.com"
    root["Subject"] = "empty-attach"
    root.attach(MIMEText("body", "plain", "utf-8"))
    part = MIMEBase("application", "pdf")
    part.set_payload(b"")
    part.add_header("Content-Disposition", "attachment", filename="empty.pdf")
    root.attach(part)
    message = parse_inbound_rfc822("9", root.as_bytes())
    assert message.subject == "empty-attach"
    assert len(message.attachments) == 1
    assert message.attachments[0].filename == "empty.pdf"
    assert message.attachments[0].available is False
    assert message.attachments[0].parse_error == "empty_payload"


def test_strip_attachment_payloads_clears_bytes_keeps_meta() -> None:
    raw = _build_multipart_with_attachment(attach_payload=b"payload-bytes")
    message = parse_inbound_rfc822("3", raw)
    stripped = strip_attachment_payloads(message)
    assert stripped.uid == "3"
    assert len(stripped.attachments) == 1
    assert stripped.attachments[0].filename == "report.bin"
    assert stripped.attachments[0].content == b""
    assert stripped.attachments[0].size == len(b"payload-bytes")
    assert stripped.attachments[0].available is False


def test_parse_html_only_does_not_copy_into_body_text() -> None:
    raw = (
        b"From: a@example.com\r\n"
        b"To: b@example.com\r\n"
        b"Subject: html-only\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: text/html; charset="utf-8"\r\n'
        b"\r\n"
        b"<html><body><p>T-Bank receipt</p></body></html>\r\n"
    )
    message = parse_inbound_rfc822("11", raw)
    assert message.body_html is not None
    assert "T-Bank receipt" in message.body_html
    assert message.body_text is None


def test_parse_inline_cid_image_sets_content_id() -> None:
    raw = (
        b"From: a@example.com\r\n"
        b"Subject: cid\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/related; boundary="b1"\r\n'
        b"\r\n"
        b"--b1\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n"
        b"\r\n"
        b'<html><body><img src="cid:logo@tbank"></body></html>\r\n'
        b"--b1\r\n"
        b"Content-Type: image/png\r\n"
        b"Content-ID: <logo@tbank>\r\n"
        b"Content-Transfer-Encoding: base64\r\n"
        b"\r\n"
        b"aW5saW5l\r\n"
        b"--b1--\r\n"
    )
    message = parse_inbound_rfc822("12", raw)
    assert message.body_html is not None
    assert "cid:logo@tbank" in message.body_html
    assert message.body_text is None
    assert len(message.attachments) == 1
    assert message.attachments[0].content_id == "logo@tbank"
    assert message.attachments[0].available is True
    assert message.attachments[0].content == b"inline"

