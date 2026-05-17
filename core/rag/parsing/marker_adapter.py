"""
Адаптер Marker → ParsedDocument (RAG-31). Типы Marker не экспортируются наружу.

Пакет marker-pdf указан в dependency-groups rag-worker (pyproject.toml); в обрезанном venv без установки — явная ошибка при вызове.
"""

from __future__ import annotations

from core.logging import get_logger
from core.rag.parsed_document import ParsedDocument

logger = get_logger(__name__)


def parse_marker_bytes(
    data: bytes,
    filename: str,
    *,
    languages: list[str],
) -> ParsedDocument:
    raise NotImplementedError("Не используется")
