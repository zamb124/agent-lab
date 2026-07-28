"""
Заметки о том, что не перенеслось при разборе markdown.

Реальные файлы содержат конструкции, которых нет в схеме wiki: сырой HTML,
списки определений, ссылки на соседние файлы. Отклонять из-за них весь файл
слишком грубо, а молча выбрасывать куски текста — потеря данных. Поэтому разбор
возвращает документ вместе со списком заметок: пользователь видит, что именно
изменилось, и решает сам.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel


class WikiMarkdownNoticeKind(StrEnum):
    """Причина расхождения между исходным markdown и документом."""

    DROPPED_HTML = "dropped_html"
    UNSUPPORTED_CONSTRUCT = "unsupported_construct"
    IMAGE_EXTRACTED = "image_extracted"
    UNRESOLVED_PAGE_LINK = "unresolved_page_link"
    FRONT_MATTER_UNKNOWN_KEY = "front_matter_unknown_key"
    OVERSIZED_DATA_URI = "oversized_data_uri"


class WikiMarkdownNotice(WikiBaseModel):
    """Одно расхождение с указанием места в исходном тексте."""

    kind: WikiMarkdownNoticeKind
    detail: str = Field(..., min_length=1)
    line: int | None = None


class WikiMarkdownNoticeCollector:
    """Накопитель заметок одного разбора.

    Состояние живёт на экземпляре, а не в модуле: разбор идёт в обработчиках
    запросов параллельно, и общий список смешивал бы заметки разных страниц.
    """

    def __init__(self) -> None:
        self._notices: list[WikiMarkdownNotice] = []

    def add(
        self, kind: WikiMarkdownNoticeKind, detail: str, line: int | None = None
    ) -> None:
        self._notices.append(WikiMarkdownNotice(kind=kind, detail=detail, line=line))

    def extend(self, notices: list[WikiMarkdownNotice]) -> None:
        self._notices.extend(notices)

    def result(self) -> list[WikiMarkdownNotice]:
        """Заметки без дублей, в порядке появления.

        Один и тот же тег обычно встречается в файле десятки раз; список из
        сорока строк про `<div>` пользователю ничего не сообщает.
        """
        seen: set[tuple[WikiMarkdownNoticeKind, str]] = set()
        unique: list[WikiMarkdownNotice] = []
        for notice in self._notices:
            key = (notice.kind, notice.detail)
            if key in seen:
                continue
            seen.add(key)
            unique.append(notice)
        return unique


__all__ = [
    "WikiMarkdownNotice",
    "WikiMarkdownNoticeCollector",
    "WikiMarkdownNoticeKind",
]
