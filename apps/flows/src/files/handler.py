"""
Извлечение вложений FilePart из A2A Message в память (без записи на диск).

A2A SDK-поля нормализуются в canonical state.files на границе канала.
"""

import base64
from dataclasses import dataclass
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

    original_name: str
    content_type: str | None
    file_size: int
    data: bytes | None = None
    uri: str | None = None


def _payload_from_bytes(file_data: FileWithBytes) -> IncomingA2aFile:
    file_bytes = base64.b64decode(file_data.bytes)
    if not file_data.name:
        raise ValueError("FileWithBytes.name обязателен")
    return IncomingA2aFile(
        original_name=file_data.name,
        content_type=file_data.mime_type,
        file_size=len(file_bytes),
        data=file_bytes,
    )


def _payload_from_uri(file_data: FileWithUri) -> IncomingA2aFile:
    if not file_data.name:
        raise ValueError("FileWithUri.name обязателен")
    return IncomingA2aFile(
        original_name=file_data.name,
        content_type=file_data.mime_type,
        file_size=0,
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

    Ожидаются canonical keys original_name, url, content_type.
    """
    if not files_data:
        return ""

    parts: list[str] = []
    for fd in files_data:
        original_name = fd.get("original_name", "")
        url = fd.get("url", "")
        content_type = fd.get("content_type", "")
        parts.append(
            f"\n[FILE]\noriginal_name: {original_name}\nurl: {url}\ncontent_type: {content_type}\n[/FILE]"
        )

    return "".join(parts)
