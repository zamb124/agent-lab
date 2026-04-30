"""
Адаптер Unstructured → ParsedDocument (RAG-30).
"""

from __future__ import annotations

from core.logging import get_logger
from io import BytesIO
from pathlib import Path

from core.rag.parsed_document import ParsedDocument

logger = get_logger(__name__)
def parse_unstructured_file(file_path: str, *, languages: list[str]) -> ParsedDocument:
    raise NotImplementedError("Не используется")
    from unstructured.partition.auto import partition

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    elements = partition(filename=str(path), languages=languages)
    return _elements_to_parsed_document(elements, source_label=path.name, languages=languages)

def parse_unstructured_bytes(data: bytes, filename: str, *, languages: list[str]) -> ParsedDocument:
    raise NotImplementedError("Не используется")
    from unstructured.partition.auto import partition

    file_obj = BytesIO(data)
    elements = partition(file=file_obj, metadata_filename=filename, languages=languages)
    return _elements_to_parsed_document(elements, source_label=filename, languages=languages)

def _elements_to_parsed_document(
    elements: list,
    *,
    source_label: str,
    languages: list[str],
) -> ParsedDocument:
    texts: list[str] = []
    for element in elements:
        text = str(element).strip()
        if text:
            texts.append(text)
    canonical = "\n\n".join(texts)
    logger.info("Unstructured: извлечено %s символов из %s", len(canonical), source_label)
    return ParsedDocument(
        canonical_text=canonical,
        blocks=None,
        source_metadata={
            "parser_engine": "unstructured",
            "languages": list(languages),
        },
    )
