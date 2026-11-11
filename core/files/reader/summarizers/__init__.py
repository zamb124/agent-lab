"""Реестр pluggable per-type суммаризаторов страниц.

Суммаризация переопределяема по типу: структурные типы (CSV/JSON/код) обрабатываются
детерминированно без LLM, остальные — default LLM-стратегией с батч-паковкой.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from core.files.reader.models import (
    CompressionMode,
    ContentMode,
    FileReadKind,
    PageResult,
    UniversalPage,
)
from core.files.reader.summarizers.base import PageSummarizer
from core.files.reader.summarizers.llm import summarize_llm_pages
from core.files.reader.summarizers.structural import (
    summarize_json_pages,
    summarize_outline_pages,
    summarize_tabular_pages,
)
from core.tracing import attributes as tattr
from core.tracing.operation_span import traced_operation
from core.types import JsonObject

_TABULAR_EXTENSIONS: frozenset[str] = frozenset({".csv", ".tsv"})
_TREE_EXTENSIONS: frozenset[str] = frozenset({".json", ".ndjson", ".xml", ".yaml", ".yml"})
_CODE_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".go", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".rb", ".rs", ".php", ".sh"}
)

SUMMARIZER_REGISTRY: dict[FileReadKind, PageSummarizer] = {
    FileReadKind.SPREADSHEET: summarize_tabular_pages,
}

DEFAULT_SUMMARIZER: PageSummarizer = summarize_llm_pages


def resolve_summarizer(*, kind: FileReadKind, file_name: str) -> PageSummarizer:
    ext = Path(file_name).suffix.lower()
    if ext in _TABULAR_EXTENSIONS:
        return summarize_tabular_pages
    if ext in _TREE_EXTENSIONS:
        return summarize_json_pages
    if ext in _CODE_EXTENSIONS:
        return summarize_outline_pages
    if kind in SUMMARIZER_REGISTRY:
        return SUMMARIZER_REGISTRY[kind]
    return DEFAULT_SUMMARIZER


async def summarize_pages(
    pages: Sequence[UniversalPage],
    *,
    kind: FileReadKind,
    file_name: str,
    prompt: str,
    model: str,
    compression: CompressionMode = CompressionMode.NEVER,
    schema: JsonObject | None = None,
) -> list[PageResult]:
    # JSON Schema / tool_choice — только LLM-путь; structural стратегии schema не умеют.
    summarizer = (
        DEFAULT_SUMMARIZER
        if schema is not None
        else resolve_summarizer(kind=kind, file_name=file_name)
    )
    async with traced_operation(
        "core.files.reader.summarize",
        operation_category="files",
        extra_attributes={
            tattr.ATTR_FILES_FILE_NAME: file_name,
            tattr.ATTR_FILES_FILE_TYPE: kind.value,
            tattr.ATTR_FILES_PAGES_COUNT: len(pages),
            tattr.ATTR_FILES_SUMMARY_MODE: (
                "llm" if summarizer is DEFAULT_SUMMARIZER else "structural"
            ),
        },
    ):
        summaries = await summarizer(
            pages,
            prompt=prompt,
            model=model,
            compression=compression,
            schema=schema,
        )
    results: list[PageResult] = []
    for page, summary in zip(pages, summaries, strict=True):
        results.append(
            PageResult(
                page=page.index,
                label=page.label,
                content_mode=ContentMode.SUMMARY,
                span_chars=len(summary),
                truncated=False,
                result=summary,
            )
        )
    return results


__all__ = [
    "PageSummarizer",
    "SUMMARIZER_REGISTRY",
    "DEFAULT_SUMMARIZER",
    "resolve_summarizer",
    "summarize_pages",
]
