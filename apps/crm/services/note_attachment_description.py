"""
Текст заметки: вставка извлечённого содержимого вложений в description.

Формат блоков совместим с resolve_note_text в note_processing_service (заголовок === ... ===).
"""

from __future__ import annotations

from typing import Optional

NOTE_ATTACHMENT_TEXT_MAX_CHARS = 100_000


def truncate_attachment_text_for_note(text: str) -> str:
    t = text.strip()
    if len(t) <= NOTE_ATTACHMENT_TEXT_MAX_CHARS:
        return t
    return t[:NOTE_ATTACHMENT_TEXT_MAX_CHARS] + "\n\n[truncated]"


def merge_attachment_extracted_into_description(
    current: Optional[str],
    display_name: str,
    extracted: str,
) -> Optional[str]:
    safe_name = display_name.strip() if isinstance(display_name, str) else ""
    if not safe_name:
        safe_name = "file"
    body = truncate_attachment_text_for_note(extracted)
    if not body:
        return current
    block = f"=== {safe_name} ===\n\n{body}"
    cur = (current or "").strip()
    if not cur:
        return block
    return f"{cur}\n\n---\n\n{block}"
