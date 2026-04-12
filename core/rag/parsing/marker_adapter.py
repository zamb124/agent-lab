"""
Адаптер Marker → ParsedDocument (RAG-31). Типы Marker не экспортируются наружу.

Пакет marker-pdf указан в dependency-groups rag-worker (pyproject.toml); в обрезанном venv без установки — явная ошибка при вызове.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from core.rag.parsed_document import ParsedDocument

logger = logging.getLogger(__name__)

# Базовая установка marker-pdf (без [full]): в README — PDF и изображения.
_MARKER_BASIC_SUFFIXES = frozenset({
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".tif",
    ".tiff",
    ".gif",
})


def parse_marker_bytes(
    data: bytes,
    filename: str,
    *,
    languages: list[str],
) -> ParsedDocument:
    """
    Парсинг байтов через Marker во временный файл (базовый PdfConverter без LLM).

    languages передаются в source_metadata (Surya/OCR — по конфигу Marker отдельно).
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in _MARKER_BASIC_SUFFIXES:
        raise ValueError(
            f"Marker (базовая установка marker-pdf): формат {suffix!r} не поддержан; "
            "укажите parsing.engine=unstructured или установите marker-pdf[full]."
        )

    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered


    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="marker_")
        os.close(fd)
        Path(tmp_path).write_bytes(data)

        converter = PdfConverter(artifact_dict=create_model_dict())
        rendered = converter(tmp_path)
        text, _meta, _images = text_from_rendered(rendered)
        canonical = (text or "").strip()
        logger.info("Marker: извлечено %s символов из %s", len(canonical), filename)

        return ParsedDocument(
            canonical_text=canonical,
            blocks=None,
            source_metadata={
                "parser_engine": "marker",
                "languages": list(languages),
                "filename": filename,
            },
        )
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)
