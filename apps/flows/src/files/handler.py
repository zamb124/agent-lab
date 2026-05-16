"""
Извлечение вложений FilePart из A2A Message в память (без записи на диск).

Имя без расширения и S3/метаданные нормализует FileProcessor.process_file_from_bytes;
канал A2A вызывает persist_uploaded_file_as_state_files_item.
"""

import base64
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from a2a.types import FilePart, FileWithBytes, FileWithUri, Message

from core.logging import get_logger

logger = get_logger(__name__)


def get_file_parts(message: Message) -> list[FilePart]:
    """Извлекает все FilePart из Message."""
    file_parts: list[FilePart] = []
    for part in message.parts:
        if isinstance(part.root, FilePart):
            file_parts.append(part.root)
        elif hasattr(part.root, "kind") and part.root.kind == "file":
            file_parts.append(part.root)
    return file_parts


@dataclass
class IncomingA2aFile:
    """Вложение из A2A: либо байты (FileWithBytes), либо URI (FileWithUri)."""

    name: str
    mime_type: str | None
    size: int
    data: bytes | None = None
    uri: str | None = None


def _payload_from_bytes(file_data: FileWithBytes) -> IncomingA2aFile:
    file_bytes = base64.b64decode(file_data.bytes)
    name = file_data.name or f"file_{uuid.uuid4().hex[:8]}"
    return IncomingA2aFile(
        name=name,
        mime_type=file_data.mime_type,
        size=len(file_bytes),
        data=file_bytes,
    )


def _payload_from_uri(file_data: FileWithUri) -> IncomingA2aFile:
    name = file_data.name or Path(file_data.uri).name or f"file_{uuid.uuid4().hex[:8]}"
    return IncomingA2aFile(
        name=name,
        mime_type=file_data.mime_type,
        size=0,
        uri=file_data.uri,
    )


def extract_incoming_a2a_files(message: Message) -> list[IncomingA2aFile]:
    """
    Извлекает вложения из Message. Байты остаются в памяти, URI не скачиваются.
    """
    file_parts = get_file_parts(message)
    if not file_parts:
        return []

    result: list[IncomingA2aFile] = []
    for file_part in file_parts:
        file_data = file_part.file
        if isinstance(file_data, FileWithBytes):
            result.append(_payload_from_bytes(file_data))
        elif isinstance(file_data, FileWithUri):
            result.append(_payload_from_uri(file_data))
        else:
            raise ValueError(f"Неподдерживаемый тип вложения A2A: {type(file_data)}")

    return result


def format_a2a_files_content(files_data: list[dict[str, Any]]) -> str:
    """
    Добавляет в текст сообщения блоки [FILE]...[/FILE] по записям для state.files.

    Ожидаются ключи name, path, mime_type (как после персиста или для URI).
    """
    if not files_data:
        return ""

    parts: list[str] = []
    for fd in files_data:
        name = fd.get("name", "")
        path = fd.get("path", "")
        mime = fd.get("mime_type") or "unknown"
        parts.append(f"\n[FILE]\nname: {name}\npath: {path}\nmime_type: {mime}\n[/FILE]")

    return "".join(parts)
