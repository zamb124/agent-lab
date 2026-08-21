"""Надёжный разбор RFC822 → InboundMailMessage.

Инвариант: любой uid с сырыми байтами даёт InboundMailMessage.
Сбой части MIME (charset, CTE, битый attach) не уничтожает письмо.
"""

from __future__ import annotations

import email
import email.policy
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import cast

from core.logging import get_logger
from core.mail.models import InboundMailMessage, MailAttachment

logger = get_logger(__name__)


def _header_str(parsed: Message, name: str) -> str | None:
    value = cast(object | None, parsed.get(name))
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return text


def parse_mail_date_header(value: str | None) -> datetime | None:
    """Date header → UTC datetime. Битый/пустой → None (письмо не падает)."""
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message_date(parsed: Message) -> datetime | None:
    return parse_mail_date_header(_header_str(parsed, "Date"))


def _to_addresses(parsed: Message) -> list[str]:
    to_header = _header_str(parsed, "To")
    if to_header is None:
        return []
    return [item.strip() for item in to_header.split(",") if item.strip()]


def _part_content_id(part: Message) -> str | None:
    raw = part.get("Content-ID")
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    if text == "":
        return None
    return text.lower()


def _is_attachment_part(part: Message) -> bool:
    disposition = str(part.get_content_disposition() or "").lower()
    if disposition == "attachment":
        return True
    filename = part.get_filename()
    if filename is not None and str(filename).strip() != "":
        return True
    content_id = _part_content_id(part)
    if content_id is None:
        return False
    content_type = part.get_content_type()
    return content_type not in ("text/plain", "text/html")


def _filename_for_part(part: Message, content_id: str | None) -> str:
    filename_raw = part.get_filename()
    filename = str(filename_raw).strip() if filename_raw is not None else ""
    if filename != "":
        return filename
    if content_id is not None:
        safe = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in content_id)
        if safe.strip("-") == "":
            return "inline"
        return f"inline-{safe}"
    return "attachment"


def _decode_text_payload(part: Message) -> str | None:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        raw = part.get_payload(decode=False)
        if isinstance(raw, str) and raw.strip():
            return raw
        return None
    if not payload:
        return None
    charset = part.get_content_charset()
    if charset is None or charset.strip() == "":
        charset = "utf-8"
    try:
        return payload.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def _extract_attachment(part: Message) -> MailAttachment:
    content_id = _part_content_id(part)
    filename = _filename_for_part(part, content_id)
    content_type = part.get_content_type()
    if not content_type or content_type.strip() == "":
        content_type = "application/octet-stream"
    try:
        payload = part.get_payload(decode=True)
    except Exception as exc:
        logger.warning(
            "mail MIME attachment payload decode failed filename=%s error=%s",
            filename,
            exc,
        )
        return MailAttachment(
            filename=filename,
            content_type=content_type,
            content=b"",
            size=0,
            available=False,
            parse_error=f"payload_decode_failed:{type(exc).__name__}",
            content_id=content_id,
        )
    if not isinstance(payload, bytes):
        return MailAttachment(
            filename=filename,
            content_type=content_type,
            content=b"",
            size=0,
            available=False,
            parse_error="payload_not_bytes",
            content_id=content_id,
        )
    if len(payload) == 0:
        return MailAttachment(
            filename=filename,
            content_type=content_type,
            content=b"",
            size=0,
            available=False,
            parse_error="empty_payload",
            content_id=content_id,
        )
    return MailAttachment(
        filename=filename,
        content_type=content_type,
        content=payload,
        size=len(payload),
        available=True,
        parse_error=None,
        content_id=content_id,
    )


def _walk_body_and_attachments(
    parsed: Message,
) -> tuple[str | None, str | None, list[MailAttachment]]:
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[MailAttachment] = []
    if parsed.is_multipart():
        for part in parsed.walk():
            content_type = part.get_content_type()
            if content_type.startswith("multipart/"):
                continue
            if _is_attachment_part(part):
                try:
                    attachments.append(_extract_attachment(part))
                except Exception as exc:
                    logger.warning(
                        "mail MIME attachment extract failed error=%s",
                        exc,
                    )
                    attachments.append(
                        MailAttachment(
                            filename="attachment",
                            content_type="application/octet-stream",
                            content=b"",
                            size=0,
                            available=False,
                            parse_error=f"extract_failed:{type(exc).__name__}",
                            content_id=_part_content_id(part),
                        )
                    )
                continue
            if content_type == "text/plain" and body_text is None:
                body_text = _decode_text_payload(part)
            elif content_type == "text/html" and body_html is None:
                body_html = _decode_text_payload(part)
    else:
        content_type = parsed.get_content_type()
        if content_type == "text/html":
            body_html = _decode_text_payload(parsed)
        else:
            body_text = _decode_text_payload(parsed)
    return body_text, body_html, attachments


def parse_inbound_rfc822(uid: str, raw_bytes: bytes) -> InboundMailMessage:
    """Собрать inbound из RFC822. Не бросает из-за битого MIME."""
    if not uid.strip():
        raise ValueError("uid is required")
    if not raw_bytes:
        return InboundMailMessage(
            uid=uid,
            message_id=None,
            subject=None,
            from_address=None,
            to_addresses=[],
            body_text=None,
            body_html=None,
            attachments=[],
        )
    try:
        parsed = email.message_from_bytes(raw_bytes, policy=email.policy.default)
    except Exception:
        try:
            parsed = email.message_from_bytes(raw_bytes, policy=email.policy.compat32)
        except Exception as exc:
            logger.warning(
                "mail MIME parse failed completely uid=%s error=%s",
                uid,
                exc,
            )
            return InboundMailMessage(
                uid=uid,
                message_id=None,
                subject=None,
                from_address=None,
                to_addresses=[],
                body_text=None,
                body_html=None,
                attachments=[],
            )
    try:
        body_text, body_html, attachments = _walk_body_and_attachments(parsed)
    except Exception as exc:
        logger.warning(
            "mail MIME walk failed uid=%s error=%s — returning headers only",
            uid,
            exc,
        )
        body_text = None
        body_html = None
        attachments = []
    return InboundMailMessage(
        uid=uid,
        message_id=_header_str(parsed, "Message-ID"),
        subject=_header_str(parsed, "Subject"),
        from_address=_header_str(parsed, "From"),
        to_addresses=_to_addresses(parsed),
        body_text=body_text,
        body_html=body_html,
        date=_message_date(parsed),
        in_reply_to=_header_str(parsed, "In-Reply-To"),
        references=_header_str(parsed, "References"),
        attachments=attachments,
    )


def strip_attachment_payloads(message: InboundMailMessage) -> InboundMailMessage:
    """Для list: метаданные вложений без байтов (экономия памяти/JSON)."""
    stripped: list[MailAttachment] = []
    for item in message.attachments:
        stripped.append(
            MailAttachment(
                filename=item.filename,
                content_type=item.content_type,
                content=b"",
                size=item.size if item.size > 0 else len(item.content),
                available=False,
                parse_error=item.parse_error if item.parse_error is not None else "list_meta_only",
                content_id=item.content_id,
            )
        )
    return message.model_copy(update={"attachments": stripped, "body_text": message.body_text})
