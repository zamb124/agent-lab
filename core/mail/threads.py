"""Группировка писем в треды по Message-ID / In-Reply-To / References."""

from __future__ import annotations

import re

from core.mail.models import InboundMailMessage

_MESSAGE_ID_TOKEN_RE = re.compile(r"<[^>\s]+>")
_SUBJECT_PREFIX_RE = re.compile(
    r"^\s*((re|fw|fwd|sv|aw|antw|ответ|пересл)\s*:\s*)+",
    re.IGNORECASE,
)


def normalize_message_id(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("message_id is required")
    if not value.startswith("<"):
        value = f"<{value}"
    if not value.endswith(">"):
        value = f"{value}>"
    return value


def parse_message_id_tokens(value: str | None) -> list[str]:
    if value is None:
        return []
    stripped = value.strip()
    if not stripped:
        return []
    tokens: list[str] = _MESSAGE_ID_TOKEN_RE.findall(stripped)
    if tokens:
        return [normalize_message_id(str(token)) for token in tokens]
    return [normalize_message_id(stripped)]


def normalize_mail_subject(subject: str | None) -> str:
    if subject is None:
        return ""
    stripped = " ".join(subject.split())
    if not stripped:
        return ""
    without_prefix = _SUBJECT_PREFIX_RE.sub("", stripped).strip()
    return without_prefix.casefold()


def collect_thread_message_ids(message: InboundMailMessage) -> set[str]:
    ids: set[str] = set()
    for raw in (message.message_id, message.in_reply_to, message.references):
        for token in parse_message_id_tokens(raw):
            ids.add(token)
    return ids


def thread_id_for_message(message: InboundMailMessage) -> str:
    references = parse_message_id_tokens(message.references)
    if references:
        return references[0]
    in_reply = parse_message_id_tokens(message.in_reply_to)
    if in_reply:
        return in_reply[0]
    own = parse_message_id_tokens(message.message_id)
    if own:
        return own[0]
    subject_key = normalize_mail_subject(message.subject)
    if subject_key:
        return f"subject:{subject_key}"
    if not message.uid.strip():
        raise ValueError("uid is required for thread_id when Message-ID headers are absent")
    return f"uid:{message.uid}"


def message_belongs_to_thread_ids(
    message: InboundMailMessage,
    *,
    thread_ids: set[str],
    subject_key: str | None,
) -> bool:
    message_ids = collect_thread_message_ids(message)
    if message_ids & thread_ids:
        return True
    if subject_key and normalize_mail_subject(message.subject) == subject_key:
        return True
    return False
