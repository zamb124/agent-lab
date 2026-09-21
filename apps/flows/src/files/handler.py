"""
Извлечение вложений Part.raw / Part.url из A2A Message (protobuf A2A 1.0).

External Part.url: байты не скачиваются здесь — SSRF-safe fetch в channel persist path
(`A2AChannel._persist_incoming_a2a_files`). Platform download URL резолвится по file_id.
"""

from dataclasses import dataclass

from a2a.types import Message, Part

from core.a2a import get_part_raw, get_part_url, part_has_raw, part_has_url
from core.logging import get_logger

logger = get_logger(__name__)


def get_file_parts(message: Message) -> list[Part]:
    """Извлекает все Part с raw или url content из Message."""
    file_parts: list[Part] = []
    for part in message.parts:
        if part_has_raw(part) or part_has_url(part):
            file_parts.append(part)
    return file_parts


@dataclass
class IncomingA2aFile:
    """Вложение из A2A: либо байты (Part.raw), либо URL (Part.url)."""

    original_name: str
    content_type: str | None
    file_size: int
    data: bytes | None = None
    uri: str | None = None


def _payload_from_raw(part: Part) -> IncomingA2aFile:
    file_bytes = get_part_raw(part)
    filename = part.filename.strip() if part.filename else ""
    if not filename:
        raise ValueError("Part.raw requires filename")
    media_type = part.media_type.strip() if part.media_type else None
    return IncomingA2aFile(
        original_name=filename,
        content_type=media_type,
        file_size=len(file_bytes),
        data=file_bytes,
    )


def _payload_from_url(part: Part) -> IncomingA2aFile:
    uri = get_part_url(part)
    if not uri.strip():
        raise ValueError("Part.url is empty")
    filename = part.filename.strip() if part.filename else ""
    if not filename:
        raise ValueError("Part.url requires filename")
    media_type = part.media_type.strip() if part.media_type else None
    return IncomingA2aFile(
        original_name=filename,
        content_type=media_type,
        file_size=0,
        uri=uri.strip(),
    )


def extract_incoming_a2a_files(message: Message) -> list[IncomingA2aFile]:
    """
    Извлекает вложения из Message.

    Part.raw — байты в памяти. Part.url — только URI (fetch в channel).
    """
    file_parts = get_file_parts(message)
    if not file_parts:
        return []

    result: list[IncomingA2aFile] = []
    for part in file_parts:
        if part_has_raw(part):
            result.append(_payload_from_raw(part))
        elif part_has_url(part):
            result.append(_payload_from_url(part))
        else:
            raise ValueError(f"Part has no raw/url: {part.WhichOneof('content')!r}")

    return result
