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
) -> list[PageResult]:
    summarizer = resolve_summarizer(kind=kind, file_name=file_name)
    summaries = await summarizer(
        pages, prompt=prompt, model=model, compression=compression
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
