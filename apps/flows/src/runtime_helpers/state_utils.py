"""Runtime helpers for flow tools."""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from core.errors import SafeEvalError
from core.files.file_ref import FileRef
from core.state import ExecutionState, PendingUIEvent
from core.types import JsonObject


def normalize_file_lookup_name(value: str | None) -> str:
    """Нормализует имя файла для устойчивого поиска в state.files."""
    if value is None:
        return ""
    text = value.strip().strip("`'\"")
    return unicodedata.normalize("NFC", text).casefold()


def normalize_file_lookup_key(value: str | None) -> str:
    normalized = normalize_file_lookup_name(value)
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def find_file(files: Sequence[FileRef], name: str | None = None) -> FileRef | None:
    """Ищет файл в state.files по original_name; без name возвращает последний файл."""
    if not files:
        return None
    if not name:
        return files[-1]
    for file_ref in files:
        if file_ref.original_name == name:
            return file_ref
    normalized_name = normalize_file_lookup_name(name)
    for file_ref in files:
        if normalize_file_lookup_name(file_ref.original_name) == normalized_name:
            return file_ref
    name_key = normalize_file_lookup_key(name)
    for file_ref in files:
        if normalize_file_lookup_key(file_ref.original_name) == name_key:
            return file_ref
    for file_ref in files:
        file_key = normalize_file_lookup_key(file_ref.original_name)
        if name_key and name_key in file_key:
            return file_ref
    return None


def push_ui_event(
    state: ExecutionState,
    event_type: str,
    payload: JsonObject,
    *,
    event_id: str | None = None,
    version: str = "1.0.0",
    source: str = "assistant",
    correlation_id: str | None = None,
) -> PendingUIEvent:
    """Добавляет UI событие в очередь ExecutionState для публикации в stream."""
    if not event_type.strip():
        raise SafeEvalError("event_type must be a non-empty string")
    if not version.strip():
        raise SafeEvalError("version must be a non-empty string")
    if not source.strip():
        raise SafeEvalError("source must be a non-empty string")

    event = PendingUIEvent(
        event_id=(
            event_id.strip() if event_id is not None and event_id.strip() else str(uuid.uuid4())
        ),
        event_type=event_type.strip(),
        payload=payload,
        version=version.strip(),
        timestamp=datetime.now(UTC).isoformat(),
        source=source.strip(),
        correlation_id=(
            correlation_id.strip()
            if correlation_id is not None and correlation_id.strip()
            else None
        ),
    )
    state.ui_events_pending.append(event)
    return event
