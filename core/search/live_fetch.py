"""Data models for live-fetch pipeline (Phase 3, §4.5.5).

This module contains only pure data classes:
    FetchedPage      — per-URL live-fetch result (markdown in-memory only)
    EvidencePassage  — evidence excerpt after heading-split + rerank

The service implementation (LiveFetchService) lives in
apps/search/services/research/live_fetch_service.py because it depends
on CrawlFetchService from apps/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

FetchTransport = Literal["http", "browser", "failed"]


@dataclass
class FetchedPage:
    """Результат live-fetch одного URL — только in-memory, не персистируется в RAG."""

    source_url: str
    canonical_url: str
    markdown: str
    content_hash: str
    fetch_transport: FetchTransport
    fetch_ms: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.fetch_transport != "failed"


@dataclass
class EvidencePassage:
    """Фрагмент страницы после heading-split + rerank (§4.5.5).

    Attributes
    ----------
    source_url:
        URL страницы, из которой извлечён фрагмент.
    heading_trail:
        Иерархия заголовков до секции (H1 → H2 → … → section_title).
    section_title:
        Заголовок секции.
    text:
        Текст фрагмента (≤ max_passage_tokens слов).
    rerank_score:
        Оценка кросс-энкодера (None если rerank не применялся).
    char_start:
        Смещение в байтах от начала markdown для citation anchor.
    """

    source_url: str
    heading_trail: list[str] = field(default_factory=list)
    section_title: str = ""
    text: str = ""
    rerank_score: float | None = None
    char_start: int | None = None
