"""Контракты поиска ссылок и описания страницы в markdown для trusted browser tools."""

from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import override
from urllib.parse import urlparse

from apps.flows.src.services.platform_facades import call_mcp_tool
from core.files.reader import FileReader
from core.state import ExecutionState
from core.types import JsonObject, parse_json_object, require_json_object

_DUCKDUCKGO_SESSION_CREATE: JsonObject = {
    "page_mode": "interactive",
    "anti_bot_tier": "gray",
    "interaction_profile": "human",
    "timeout_ms": 120000,
    "context": {
        "page_mode": "interactive",
        "anti_bot_tier": "gray",
        "stealth_init_version": "v1",
        "interaction_profile": "human",
    },
}

_CRAWL_SESSION_CREATE: JsonObject = {
    "page_mode": "crawl",
    "anti_bot_tier": "gray",
    "interaction_profile": "human",
    "timeout_ms": 120000,
    "context": {
        "page_mode": "crawl",
        "anti_bot_tier": "gray",
        "stealth_init_version": "v1",
        "interaction_profile": "human",
    },
}


def _normalize_ref(raw_ref: str) -> str:
    value = raw_ref.strip()
    if value == "":
        raise ValueError("Пустой ref")
    if value.startswith("@"):
        return value
    return f"@{value}"


def _pick_search_ref(snapshot_text: str) -> str:
    for line in snapshot_text.splitlines():
        low = line.lower()
        if ("combobox" not in low) and ("searchbox" not in low) and ("textbox" not in low):
            continue
        match = re.search(r"ref=([^\]\s]+)", line)
        if match is None:
            continue
        return _normalize_ref(match.group(1))
    raise ValueError("Не найден ref поля поиска в snapshot.text")


def _extract_links(
    snapshot_text: str,
    *,
    per_query_limit: int,
    blocked_hosts: tuple[str, ...],
) -> list[str]:
    urls: list[str] = re.findall(r"https?://[^\s\]\\\"\')]+", snapshot_text)
    links: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = raw.rstrip(".,)")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc == "":
            continue
        host = parsed.netloc.lower()
        if any(blocked in host for blocked in blocked_hosts):
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
        if len(links) >= per_query_limit:
            break
    return links


def _required_text(payload: JsonObject, field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


async def _mcp_json(
    server_id: str,
    state: ExecutionState,
    tool_name: str,
    arguments: JsonObject,
) -> JsonObject:
    result = await call_mcp_tool(
        server_id=server_id,
        tool_name=tool_name,
        arguments=arguments,
        state=state,
    )
    if result.is_error:
        raise ValueError(f"MCP {tool_name} вернул is_error=true")
    if len(result.content) == 0:
        raise ValueError(f"MCP {tool_name} вернул пустой content")
    first = result.content[0]
    text = first.get("text")
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError(f"MCP {tool_name}: пустой text")
    return parse_json_object(text, f"MCP {tool_name}.text")


class Search(ABC):
    """Поиск URL по текстовому запросу."""

    @abstractmethod
    async def links(self, state: ExecutionState, query: str) -> list[str]:
        """Возвращает список HTTP(S) URL, релевантных запросу."""


class Describe(ABC):
    """Получение markdown-текста страницы по URL."""

    @abstractmethod
    async def page_markdown(self, state: ExecutionState, url: str) -> str:
        """Возвращает markdown-содержимое страницы."""


class DuckDuckGoBrowserSearch(Search):
    """
    Поиск ссылок через DuckDuckGo в браузере (MCP browser).

    Поведение совпадает с нодой search_duckduckgo_batch в simple_crawler.
    """

    def __init__(
        self,
        *,
        server_id: str = "browser",
        per_query_limit: int = 5,
        blocked_hosts: tuple[str, ...] = ("duckduckgo.com",),
    ) -> None:
        if server_id.strip() == "":
            raise ValueError("server_id обязателен")
        if per_query_limit < 1:
            raise ValueError("per_query_limit должен быть >= 1")
        self._server_id: str = server_id.strip()
        self._per_query_limit: int = per_query_limit
        self._blocked_hosts: tuple[str, ...] = blocked_hosts

    @override
    async def links(self, state: ExecutionState, query: str) -> list[str]:
        if query.strip() == "":
            raise ValueError("query обязателен")
        return await self._duckduckgo_one_query(state, query.strip())

    async def links_many(self, state: ExecutionState, queries: list[str]) -> list[str]:
        """Несколько запросов параллельно; URL дедуплицируются в порядке первого появления."""
        coroutines: list[Awaitable[list[str]]] = []
        for raw in queries:
            q = raw.strip()
            if q == "":
                continue
            coroutines.append(self._duckduckgo_one_query(state, q))
        if len(coroutines) == 0:
            raise ValueError("queries: нет непустых запросов")
        batches = await asyncio.gather(*coroutines)
        out: list[str] = []
        seen: set[str] = set()
        for batch in batches:
            for link in batch:
                if link in seen:
                    continue
                seen.add(link)
                out.append(link)
        return out

    async def _duckduckgo_one_query(self, state: ExecutionState, q: str) -> list[str]:
        created = await _mcp_json(
            self._server_id,
            state,
            "browser_create_session",
            dict(_DUCKDUCKGO_SESSION_CREATE),
        )
        session_id = _required_text(created, "session_id")
        try:
            _ = await _mcp_json(
                self._server_id,
                state,
                "browser_navigate",
                {
                    "session_id": session_id,
                    "url": "https://duckduckgo.com/",
                    "wait_policy": "domcontentloaded",
                    "navigation_timeout_ms": 45000,
                },
            )
            observed = await _mcp_json(
                self._server_id,
                state,
                "browser_observe",
                {
                    "session_id": session_id,
                    "include_snapshot_refs": False,
                },
            )
            snapshot = require_json_object(observed["snapshot"], "browser_observe.snapshot")
            snapshot_text = _required_text(snapshot, "text")
            search_ref = _pick_search_ref(snapshot_text)
            _ = await _mcp_json(
                self._server_id,
                state,
                "browser_fill",
                {
                    "session_id": session_id,
                    "ref": search_ref,
                    "text": q,
                    "timeout_ms": 15000,
                    "typing_delay_ms": 95,
                },
            )
            _ = await _mcp_json(
                self._server_id,
                state,
                "browser_press",
                {
                    "session_id": session_id,
                    "key": "Enter",
                },
            )
            _ = await _mcp_json(
                self._server_id,
                state,
                "browser_wait",
                {
                    "session_id": session_id,
                    "selector": "a[data-testid='result-title-a'], h2 a",
                    "timeout_ms": 60000,
                },
            )
            results_observe = await _mcp_json(
                self._server_id,
                state,
                "browser_observe",
                {
                    "session_id": session_id,
                    "include_snapshot_refs": False,
                },
            )
            results_snapshot = require_json_object(
                results_observe["snapshot"],
                "browser_observe.results.snapshot",
            )
            result_text = _required_text(results_snapshot, "text")
            return _extract_links(
                result_text,
                per_query_limit=self._per_query_limit,
                blocked_hosts=self._blocked_hosts,
            )
        finally:
            _ = await _mcp_json(
                self._server_id,
                state,
                "browser_close_session",
                {"session_id": session_id},
            )


class BrowserSnapshotDescribe(Describe):
    """
    Снимок HTML в S3 и чтение markdown через FileReader (MCP browser).

    Поведение совпадает с цепочкой crawl_pages_recursive + html_to_markdown_batch в simple_crawler.
    """

    def __init__(
        self,
        *,
        server_id: str = "browser",
        navigation_timeout_ms: int = 30000,
        ingest_source: str = "simple_crawler",
        file_reader: FileReader | None = None,
    ) -> None:
        if server_id.strip() == "":
            raise ValueError("server_id обязателен")
        if navigation_timeout_ms < 1:
            raise ValueError("navigation_timeout_ms должен быть >= 1")
        if ingest_source.strip() == "":
            raise ValueError("ingest_source обязателен")
        self._server_id: str = server_id.strip()
        self._navigation_timeout_ms: int = navigation_timeout_ms
        self._ingest_source: str = ingest_source.strip()
        self._file_reader: FileReader | None = file_reader

    async def _save_html_read_markdown(
        self,
        state: ExecutionState,
        page_url: str,
    ) -> tuple[str, str, str, str]:
        reader = self._file_reader if self._file_reader is not None else FileReader()
        created = await _mcp_json(
            self._server_id,
            state,
            "browser_create_session",
            dict(_CRAWL_SESSION_CREATE),
        )
        session_id = _required_text(created, "session_id")
        try:
            _ = await _mcp_json(
                self._server_id,
                state,
                "browser_navigate",
                {
                    "session_id": session_id,
                    "url": page_url,
                    "wait_policy": "domcontentloaded",
                    "navigation_timeout_ms": self._navigation_timeout_ms,
                },
            )
            saved = await _mcp_json(
                self._server_id,
                state,
                "browser_save_html_to_s3",
                {
                    "session_id": session_id,
                    "original_name": "snapshot.html",
                    "links_limit": 10,
                    "metadata": {
                        "source_url": page_url,
                        "source": self._ingest_source,
                    },
                },
            )
            file_id = _required_text(saved, "file_id")
            s3_path = _required_text(saved, "s3_path")
            source_url = _required_text(saved, "source_url")
        finally:
            _ = await _mcp_json(
                self._server_id,
                state,
                "browser_close_session",
                {"session_id": session_id},
            )

        read_result = await reader.read(
            "",
            file_name="snapshot.html",
            source_file_id=file_id,
        )
        if len(read_result.pages) == 0:
            raise ValueError("FileReader: нет страниц в результате")
        text = str(read_result.pages[0].text).strip()
        if text == "":
            raise ValueError("FileReader: пустой markdown")
        return file_id, s3_path, source_url, text

    async def page_snapshot(self, state: ExecutionState, url: str) -> dict[str, str]:
        """
        URL после навигации, идентификаторы файла в хранилище и markdown-текст страницы.

        Ключи: ``url``, ``file_id``, ``s3_path``, ``text``.
        """
        if url.strip() == "":
            raise ValueError("url обязателен")
        page_url = url.strip()
        file_id, s3_path, source_url, text = await self._save_html_read_markdown(state, page_url)
        return {
            "url": source_url,
            "file_id": file_id,
            "s3_path": s3_path,
            "text": text,
        }

    @override
    async def page_markdown(self, state: ExecutionState, url: str) -> str:
        if url.strip() == "":
            raise ValueError("url обязателен")
        _file_id, _s3_path, _src, text = await self._save_html_read_markdown(state, url.strip())
        return text
