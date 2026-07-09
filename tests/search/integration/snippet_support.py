"""Хелперы проверки SERP-сниппетов."""

from __future__ import annotations


def strip_snippet_highlight(snippet: str) -> str:
    """
    Убирает markdown-подсветку ``ts_headline`` (StartSel/StopSel = ``**``)
    для substring-ассертов по содержимому сниппета.
    """
    return snippet.replace("**", "")
