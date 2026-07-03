"""Контракт per-type суммаризатора страниц."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from core.files.reader.models import UniversalPage


class PageSummarizer(Protocol):
    """Стратегия суммаризации набора Universal Pages.

    Возвращает список summary-строк той же длины и порядка, что ``pages``.
    Структурные стратегии детерминированы и LLM не зовут; default-стратегия
    пакует страницы в контекстное окно summarization-модели.
    """

    async def __call__(
        self,
        pages: Sequence[UniversalPage],
        *,
        prompt: str,
        model: str,
    ) -> list[str]: ...
