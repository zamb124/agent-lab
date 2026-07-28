"""
Граница markdown-файла: front matter и тело.

Свойства страницы (заголовок, иконка, обложка) живут в колонках БД, а не в
содержимом. При экспорте они выносятся в YAML-заголовок файла, при импорте —
читаются оттуда. Само содержимое от этого не зависит: `document_to_markdown`
остаётся чистым, потому что тот же текст попадает в `text_markdown` и в RAG, где
служебная шапка была бы мусором.

Формат тот же, что у SKILL.md агентских навыков: `---`, YAML, `---`.
"""

from __future__ import annotations

import re
from typing import Final, cast

import yaml
from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.markdown_notices import WikiMarkdownNotice, WikiMarkdownNoticeKind

_FRONT_MATTER_RE: Final[re.Pattern[str]] = re.compile(
    r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL
)

TITLE_KEY: Final[str] = "title"
ICON_KEY: Final[str] = "icon"
COVER_KEY: Final[str] = "cover_url"

KNOWN_KEYS: Final[frozenset[str]] = frozenset({TITLE_KEY, ICON_KEY, COVER_KEY})


class WikiMarkdownFrontMatter(WikiBaseModel):
    """Свойства страницы из шапки файла.

    `None` означает «в файле не задано» и отличается от пустой строки: пустая
    строка это осознанное «убрать обложку», отсутствие ключа — «не трогать».
    """

    title: str | None = Field(default=None, max_length=500)
    icon: str | None = Field(default=None, max_length=64)
    cover_url: str | None = None


class WikiMarkdownFileParts(WikiBaseModel):
    """Файл, разложенный на шапку и тело."""

    front_matter: WikiMarkdownFrontMatter = Field(default_factory=WikiMarkdownFrontMatter)
    body: str = ""
    notices: list[WikiMarkdownNotice] = Field(default_factory=list)


def split_markdown_file(text: str) -> WikiMarkdownFileParts:
    """Отделить YAML-шапку от тела markdown.

    Нечитаемый YAML — не повод отказать во всём файле: шапка теряется, тело
    импортируется, о расхождении сообщает заметка.
    """
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        return WikiMarkdownFileParts(body=text)

    body = text[match.end() :]
    notices: list[WikiMarkdownNotice] = []
    loaded: object
    try:
        loaded = cast("object", yaml.safe_load(match.group(1)))
    except yaml.YAMLError as exc:
        return WikiMarkdownFileParts(
            body=body,
            notices=[
                WikiMarkdownNotice(
                    kind=WikiMarkdownNoticeKind.FRONT_MATTER_UNKNOWN_KEY,
                    detail=f"YAML-шапка не разобрана: {exc}",
                    line=1,
                )
            ],
        )

    if not isinstance(loaded, dict):
        return WikiMarkdownFileParts(
            body=body,
            notices=[
                WikiMarkdownNotice(
                    kind=WikiMarkdownNoticeKind.FRONT_MATTER_UNKNOWN_KEY,
                    detail="YAML-шапка не является набором ключей",
                    line=1,
                )
            ],
        )

    # YAML отдаёт нетипизированное дерево; дальше по коду идут только строки.
    header = cast("dict[object, object]", loaded)
    values: dict[str, str] = {}
    for key, value in header.items():
        name = str(key)
        if name not in KNOWN_KEYS:
            notices.append(
                WikiMarkdownNotice(
                    kind=WikiMarkdownNoticeKind.FRONT_MATTER_UNKNOWN_KEY,
                    detail=f"ключ шапки {name} страницей не используется",
                    line=1,
                )
            )
            continue
        values[name] = "" if value is None else str(value)

    return WikiMarkdownFileParts(
        front_matter=WikiMarkdownFrontMatter(
            title=values.get(TITLE_KEY),
            icon=values.get(ICON_KEY),
            cover_url=values.get(COVER_KEY),
        ),
        body=body,
        notices=notices,
    )


def compose_markdown_file(
    *, title: str, icon: str, cover_url: str, body: str
) -> str:
    """Файл для экспорта: шапка со свойствами страницы плюс тело.

    Пустые свойства в шапку не попадают — иначе повторный импорт затирал бы
    заголовок пустой строкой.
    """
    header: dict[str, str] = {}
    if title:
        header[TITLE_KEY] = title
    if icon:
        header[ICON_KEY] = icon
    if cover_url:
        header[COVER_KEY] = cover_url

    if not header:
        return f"{body}\n" if body else ""

    rendered = yaml.safe_dump(header, allow_unicode=True, sort_keys=True).strip()
    return f"---\n{rendered}\n---\n\n{body}\n" if body else f"---\n{rendered}\n---\n"


def markdown_file_name(title: str, wiki_page_id: str) -> str:
    """Имя файла для выгрузки: по заголовку, с запасным вариантом на id."""
    slug = re.sub(r"[^\w\- ]+", "", title, flags=re.UNICODE).strip()
    slug = re.sub(r"\s+", "-", slug)
    return f"{slug or wiki_page_id}.md"


__all__ = [
    "COVER_KEY",
    "ICON_KEY",
    "KNOWN_KEYS",
    "TITLE_KEY",
    "WikiMarkdownFileParts",
    "WikiMarkdownFrontMatter",
    "compose_markdown_file",
    "markdown_file_name",
    "split_markdown_file",
]
