"""Контракт per-type суммаризатора страниц."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from core.files.reader.models import CompressionMode, UniversalPage
from core.types import JsonObject


class PageSummarizer(Protocol):
    """Стратегия суммаризации набора Universal Pages.

    Возвращает список summary-строк той же длины и порядка, что ``pages``.
    Структурные стратегии детерминированы и LLM не зовут; default-стратегия
    пакует страницы в контекстное окно и при nested images шлёт multimodal
    (текст + Part(raw)) через llm_vision. При ``schema`` — forced tool
    ``submit_page_summary`` (по одной странице), result — JSON arguments.
    """

    async def __call__(
        self,
        pages: Sequence[UniversalPage],
        *,
        prompt: str,
        model: str,
        compression: CompressionMode = CompressionMode.NEVER,
        schema: JsonObject | None = None,
    ) -> list[str]: ...
