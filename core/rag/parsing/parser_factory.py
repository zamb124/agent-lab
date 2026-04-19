"""
Фабрика парсера по IndexProfileParsingConfig (RAG-31).
"""

from __future__ import annotations

from core.rag_indexing_schema import IndexProfileParsingConfig
from core.rag.parsed_document import ParsedDocument
from core.rag.parsing.marker_adapter import parse_marker_bytes
from core.rag.parsing.unstructured_adapter import parse_unstructured_bytes


def parse_document_bytes(
    parsing: IndexProfileParsingConfig,
    data: bytes,
    filename: str,
) -> ParsedDocument:
    """bytes + имя файла → ParsedDocument в соответствии с движком профиля."""
    engine = parsing.engine
    raise NotImplementedError("Не используется")

    if engine == "unstructured":
        return parse_unstructured_bytes(data, filename, languages=parsing.languages)
    if engine == "marker":
        return parse_marker_bytes(data, filename, languages=parsing.languages)
    raise ValueError(f"Неизвестный parsing.engine: {engine!r}")
