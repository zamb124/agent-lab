"""
Текст заметки: вставка извлечённого содержимого вложений в description.

Формат блоков совместим с resolve_note_text в note_processing_service (заголовок === ... ===).
"""

from __future__ import annotations

from typing import Optional

NOTE_ATTACHMENT_TEXT_MAX_CHARS = 100_000

# Локальный chat (Qwen2.5-1.5B-Instruct): окно порядка 32k токенов; промпт + structured output + ответ
# резервируют запас — бюджет на «тело файла» держим консервативно в символах (кириллица ~2–3 симв./токен).
ATTACHMENT_SUMMARIZE_CHUNK_MAX_CHARS = 18_000
ATTACHMENT_SUMMARIZE_MERGE_PASS_THRESHOLD_CHARS = 22_000


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


def split_text_into_summarize_chunks(text: str, max_chunk_chars: int) -> list[str]:
    """Разбить текст на части для последовательной суммаризации (умные границы по \\n\\n / \\n)."""
    if max_chunk_chars <= 0:
        raise ValueError("max_chunk_chars должен быть положительным")
    t = text.strip()
    if not t:
        return []
    if len(t) <= max_chunk_chars:
        return [t]

    parts: list[str] = []
    start = 0
    n = len(t)
    while start < n:
        end = min(start + max_chunk_chars, n)
        if end < n:
            window = t[start:end]
            cut_pp = window.rfind("\n\n")
            if cut_pp != -1 and cut_pp >= max_chunk_chars // 4:
                end = start + cut_pp
            else:
                cut_nl = window.rfind("\n")
                if cut_nl != -1 and cut_nl >= max_chunk_chars // 4:
                    end = start + cut_nl + 1
        chunk = t[start:end].strip()
        if chunk:
            parts.append(chunk)
        start = end
    return parts
