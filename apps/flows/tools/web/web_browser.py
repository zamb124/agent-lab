"""Платформенные тулы браузера для ReAct: DuckDuckGo-поиск ссылок и снимок страницы в markdown."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from apps.flows.src.services.browser_client import BrowserClient
from apps.flows.src.tools.decorator import tool
from core.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from apps.flows.src.state import ExecutionState

DEFAULT_BROWSER_MARKDOWN_MAX_CHARS = 12_000


_BROWSER_DUCKDUCKGO_LINKS_DESCRIPTION = """
Поиск HTTP(S) URL по текстовому запросу через DuckDuckGo в браузере (MCP `browser`).

Поведение совпадает с нодой simple_crawler `search_duckduckgo_batch`.

Ответ: `urls` (список строк, до `per_query_limit` штук). Ошибки — исключение.

Параметры:
- `query` (строка): поисковая фраза.
- `server_id` (строка, по умолчанию `browser`): id MCP-сервера браузера из конфигурации компании.
- `per_query_limit` (целое, по умолчанию 5, 1–50): максимум ссылок на один запрос.

Когда вызывать: нужно получить набор ссылок из веб-поиска перед обходом страниц.
""".strip()

_BROWSER_DUCKDUCKGO_LINKS_BATCH_DESCRIPTION = """
Несколько поисковых запросов параллельно; URL из всех запросов объединяются с дедупликацией (порядок первого появления).

Ответ: `urls`. Ошибки — исключение.

Параметры:
- `queries` (массив строк): хотя бы одна непустая строка после trim.
- `server_id`, `per_query_limit` — как у `browser_duckduckgo_links`.

Когда вызывать: несколько формулировок запроса за один шаг.
""".strip()

_BROWSER_PAGE_MARKDOWN_DESCRIPTION = """
Открывает URL в режиме crawl, сохраняет HTML в S3 через MCP, читает markdown через `FileReader`.

Ответ: `markdown`, `truncated`, `original_chars`, `max_markdown_chars`. Ошибки — исключение.

Параметры:
- `url` (строка): HTTP(S) адрес страницы.
- `server_id` (строка, по умолчанию `browser`).
- `navigation_timeout_ms` (целое, по умолчанию 30000, ≥1): таймаут навигации.
- `ingest_source` (строка, по умолчанию `simple_crawler`): метаданные `source` для загрузки в S3.
- `max_markdown_chars` (целое, по умолчанию 12000): жесткий лимит markdown, передаваемого обратно в LLM.

Когда вызывать: нужен текст страницы для анализа без полей `file_id` / `s3_path`.
""".strip()

_BROWSER_PAGE_SNAPSHOT_DESCRIPTION = """
То же получение контента, что и `browser_page_markdown`, плюс идентификаторы артефакта в хранилище.

Ответ: `url`, `file_id`, `s3_path`, `text` (markdown), `truncated`, `original_chars`, `max_markdown_chars`.
Ошибки — исключение.

Параметры: как у `browser_page_markdown`.

Когда вызывать: нужен markdown и ссылки на файл в платформе (дальнейшее чтение, вложения, трейсинг).
""".strip()


def bound_browser_markdown(markdown: str, max_markdown_chars: int) -> tuple[str, bool]:
    if max_markdown_chars < 1:
        raise ValueError("max_markdown_chars must be positive")
    if len(markdown) <= max_markdown_chars:
        return markdown, False
    suffix = (
        "\n\n[markdown truncated "
        f"original_chars={len(markdown)} max_markdown_chars={max_markdown_chars}]"
    )
    body_limit = max(max_markdown_chars - len(suffix), 0)
    return markdown[:body_limit].rstrip() + suffix, True


class BrowserDuckduckgoLinksArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, description="Поисковая фраза.")
    server_id: str = Field("browser", min_length=1, description="Id MCP-сервера браузера.")
    per_query_limit: int = Field(5, ge=1, le=50, description="Максимум URL на запрос.")


class BrowserDuckduckgoLinksBatchArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    queries: list[str] = Field(
        ...,
        min_length=1,
        description="Список поисковых фраз; хотя бы одна непустая после нормализации.",
    )
    server_id: str = Field("browser", min_length=1, description="Id MCP-сервера браузера.")
    per_query_limit: int = Field(5, ge=1, le=50, description="Максимум URL на запрос.")

    @field_validator("queries", mode="before")
    @classmethod
    def _normalize_queries(cls, value: JsonValue) -> list[str]:
        if not isinstance(value, list):
            raise TypeError("queries must be an array of strings")
        out: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise TypeError(f"queries[{index}] must be a string")
            s = item.strip()
            if s != "":
                out.append(s)
        if len(out) == 0:
            raise ValueError("queries: no non-empty strings")
        return out


class BrowserPageMarkdownArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(..., min_length=1, description="HTTP(S) URL страницы.")
    server_id: str = Field("browser", min_length=1, description="Id MCP-сервера браузера.")
    navigation_timeout_ms: int = Field(30000, ge=1, description="Таймаут навигации, мс.")
    ingest_source: str = Field(
        "simple_crawler",
        min_length=1,
        description="Метаданные source для загрузки HTML в S3.",
    )
    max_markdown_chars: int = Field(
        DEFAULT_BROWSER_MARKDOWN_MAX_CHARS,
        ge=1,
        le=50_000,
        description="Жёсткий лимит символов markdown в ответе.",
    )


class BrowserPageSnapshotArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: str = Field(..., min_length=1, description="HTTP(S) URL страницы.")
    server_id: str = Field("browser", min_length=1, description="Id MCP-сервера браузера.")
    navigation_timeout_ms: int = Field(30000, ge=1, description="Таймаут навигации, мс.")
    ingest_source: str = Field(
        "simple_crawler",
        min_length=1,
        description="Метаданные source для загрузки HTML в S3.",
    )
    max_markdown_chars: int = Field(
        DEFAULT_BROWSER_MARKDOWN_MAX_CHARS,
        ge=1,
        le=50_000,
        description="Жёсткий лимит символов markdown в ответе.",
    )


@tool(
    name="browser_duckduckgo_links",
    description=_BROWSER_DUCKDUCKGO_LINKS_DESCRIPTION,
    tags=["web"],
    parameters_model=BrowserDuckduckgoLinksArgs,
)
async def browser_duckduckgo_links(
    query: str,
    server_id: str = "browser",
    per_query_limit: int = 5,
    *,
    state: "ExecutionState",
) -> JsonObject:
    urls = await BrowserClient().duckduckgo_links(
        state,
        query,
        server_id=server_id,
        per_query_limit=per_query_limit,
    )
    return {"urls": urls}


@tool(
    name="browser_duckduckgo_links_batch",
    description=_BROWSER_DUCKDUCKGO_LINKS_BATCH_DESCRIPTION,
    tags=["web"],
    parameters_model=BrowserDuckduckgoLinksBatchArgs,
)
async def browser_duckduckgo_links_batch(
    queries: list[str],
    server_id: str = "browser",
    per_query_limit: int = 5,
    *,
    state: "ExecutionState",
) -> JsonObject:
    urls = await BrowserClient().duckduckgo_links_batch(
        state,
        queries,
        server_id=server_id,
        per_query_limit=per_query_limit,
    )
    return {"urls": urls}


@tool(
    name="browser_page_markdown",
    description=_BROWSER_PAGE_MARKDOWN_DESCRIPTION,
    tags=["web"],
    parameters_model=BrowserPageMarkdownArgs,
)
async def browser_page_markdown(
    url: str,
    server_id: str = "browser",
    navigation_timeout_ms: int = 30000,
    ingest_source: str = "simple_crawler",
    max_markdown_chars: int = DEFAULT_BROWSER_MARKDOWN_MAX_CHARS,
    *,
    state: "ExecutionState",
) -> JsonObject:
    try:
        markdown = await BrowserClient().page_markdown(
            state,
            url,
            server_id=server_id,
            navigation_timeout_ms=navigation_timeout_ms,
            ingest_source=ingest_source,
        )
    except Exception as exc:
        # Контракт tool/public_search: success=false при недоступном browser MCP /
        # сетевых сбоях — не ронять code-node через capability 500.
        return {
            "success": False,
            "error": str(exc),
            "markdown": "",
            "truncated": False,
            "original_chars": 0,
            "max_markdown_chars": max_markdown_chars,
        }
    bounded_markdown, truncated = bound_browser_markdown(markdown, max_markdown_chars)
    return {
        "success": True,
        "markdown": bounded_markdown,
        "truncated": truncated,
        "original_chars": len(markdown),
        "max_markdown_chars": max_markdown_chars,
    }


@tool(
    name="browser_page_snapshot",
    description=_BROWSER_PAGE_SNAPSHOT_DESCRIPTION,
    tags=["web"],
    parameters_model=BrowserPageSnapshotArgs,
)
async def browser_page_snapshot(
    url: str,
    server_id: str = "browser",
    navigation_timeout_ms: int = 30000,
    ingest_source: str = "simple_crawler",
    max_markdown_chars: int = DEFAULT_BROWSER_MARKDOWN_MAX_CHARS,
    *,
    state: "ExecutionState",
) -> JsonObject:
    snap = await BrowserClient().page_snapshot(
        state,
        url,
        server_id=server_id,
        navigation_timeout_ms=navigation_timeout_ms,
        ingest_source=ingest_source,
    )
    raw_text = snap.get("text")
    if not isinstance(raw_text, str):
        raise TypeError("browser_page_snapshot: text must be string")
    text, truncated = bound_browser_markdown(raw_text, max_markdown_chars)
    return {
        **snap,
        "text": text,
        "truncated": truncated,
        "original_chars": len(raw_text),
        "max_markdown_chars": max_markdown_chars,
    }
