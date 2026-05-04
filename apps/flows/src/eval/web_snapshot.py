"""
Контракты поиска ссылок и описания страницы в markdown для inline eval.

Реализации по умолчанию совпадают с бандлом simple_crawler (MCP browser, FileReader).
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from typing import Any, Awaitable
from urllib.parse import urlparse

from apps.flows.src.eval.platform_services import call_mcp_tool
from core.files.reader import FileReader

_DUCKDUCKGO_SESSION_CREATE: dict[str, Any] = {
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

_CRAWL_SESSION_CREATE: dict[str, Any] = {
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
    urls = re.findall(r"https?://[^\s\]\\\"\')]+", snapshot_text)
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


async def _mcp_json(
    server_id: str,
    state: Any,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    result = await call_mcp_tool(
        server_id=server_id,
        tool_name=tool_name,
        arguments=arguments,
        state=state,
    )
    if result.is_error:
        raise ValueError(f"MCP {tool_name} вернул is_error=true")
    if not isinstance(result.content, list) or len(result.content) == 0:
        raise ValueError(f"MCP {tool_name} вернул пустой content")
    first = result.content[0]
    if not isinstance(first, dict):
        raise ValueError(f"MCP {tool_name}: content[0] должен быть dict")
    text = first.get("text")
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError(f"MCP {tool_name}: пустой text")
    return json.loads(text)


class Search(ABC):
    """Поиск URL по текстовому запросу."""

    @abstractmethod
    async def links(self, state: Any, query: str) -> list[str]:
        """Возвращает список HTTP(S) URL, релевантных запросу."""


class Describe(ABC):
    """Получение markdown-текста страницы по URL."""

    @abstractmethod
    async def page_markdown(self, state: Any, url: str) -> str:
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
        if not isinstance(server_id, str) or server_id.strip() == "":
            raise ValueError("server_id обязателен")
        if per_query_limit < 1:
            raise ValueError("per_query_limit должен быть >= 1")
        self._server_id = server_id.strip()
        self._per_query_limit = per_query_limit
        self._blocked_hosts = blocked_hosts

    async def links(self, state: Any, query: str) -> list[str]:
        if not isinstance(query, str) or query.strip() == "":
            raise ValueError("query обязателен")
        return await self._duckduckgo_one_query(state, query.strip())

    async def links_many(self, state: Any, queries: list[str]) -> list[str]:
        """Несколько запросов параллельно; URL дедуплицируются в порядке первого появления."""
        coroutines: list[Awaitable[list[str]]] = []
        for raw in queries:
            q = str(raw).strip()
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

    async def _duckduckgo_one_query(self, state: Any, q: str) -> list[str]:
        created = await _mcp_json(
            self._server_id,
            state,
            "browser_create_session",
            dict(_DUCKDUCKGO_SESSION_CREATE),
        )
        session_id = str(created.get("session_id", "")).strip()
        if session_id == "":
            raise ValueError("browser_create_session не вернул session_id")
        try:
            await _mcp_json(
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
            snapshot = observed.get("snapshot")
            if not isinstance(snapshot, dict):
                raise ValueError("browser_observe: snapshot отсутствует")
            snapshot_text = str(snapshot.get("text", "")).strip()
            if snapshot_text == "":
                raise ValueError("browser_observe: пустой snapshot.text")
            search_ref = _pick_search_ref(snapshot_text)
            await _mcp_json(
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
            await _mcp_json(
                self._server_id,
                state,
                "browser_press",
                {
                    "session_id": session_id,
                    "key": "Enter",
                },
            )
            await _mcp_json(
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
            results_snapshot = results_observe.get("snapshot")
            if not isinstance(results_snapshot, dict):
                raise ValueError("browser_observe results: snapshot отсутствует")
            result_text = str(results_snapshot.get("text", "")).strip()
            return _extract_links(
                result_text,
                per_query_limit=self._per_query_limit,
                blocked_hosts=self._blocked_hosts,
            )
        finally:
            await _mcp_json(
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
        if not isinstance(server_id, str) or server_id.strip() == "":
            raise ValueError("server_id обязателен")
        if navigation_timeout_ms < 1:
            raise ValueError("navigation_timeout_ms должен быть >= 1")
        if not isinstance(ingest_source, str) or ingest_source.strip() == "":
            raise ValueError("ingest_source обязателен")
        self._server_id = server_id.strip()
        self._navigation_timeout_ms = navigation_timeout_ms
        self._ingest_source = ingest_source.strip()
        self._file_reader = file_reader

    async def _save_html_read_markdown(
        self,
        state: Any,
        page_url: str,
    ) -> tuple[str, str, str, str]:
        reader = self._file_reader if self._file_reader is not None else FileReader()
        created = await _mcp_json(
            self._server_id,
            state,
            "browser_create_session",
            dict(_CRAWL_SESSION_CREATE),
        )
        session_id = str(created.get("session_id", "")).strip()
        if session_id == "":
            raise ValueError("browser_create_session не вернул session_id")
        try:
            await _mcp_json(
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
            file_id = str(saved.get("file_id", "")).strip()
            s3_path = str(saved.get("s3_path", "")).strip()
            source_url = str(saved.get("source_url", page_url)).strip()
            if file_id == "" or s3_path == "":
                raise ValueError("browser_save_html_to_s3 вернул пустой file_id/s3_path")
        finally:
            await _mcp_json(
                self._server_id,
                state,
                "browser_close_session",
                {"session_id": session_id},
            )

        read_result = await reader.read({"file_id": file_id, "name": "snapshot.html"})
        if len(read_result.pages) == 0:
            raise ValueError("FileReader: нет страниц в результате")
        text = str(read_result.pages[0].text).strip()
        if text == "":
            raise ValueError("FileReader: пустой markdown")
        return file_id, s3_path, source_url, text

    async def page_snapshot(self, state: Any, url: str) -> dict[str, str]:
        """
        URL после навигации, идентификаторы файла в хранилище и markdown-текст страницы.

        Ключи: ``url``, ``file_id``, ``s3_path``, ``text``.
        """
        if not isinstance(url, str) or url.strip() == "":
            raise ValueError("url обязателен")
        page_url = url.strip()
        file_id, s3_path, source_url, text = await self._save_html_read_markdown(state, page_url)
        return {
            "url": source_url,
            "file_id": file_id,
            "s3_path": s3_path,
            "text": text,
        }

    async def page_markdown(self, state: Any, url: str) -> str:
        if not isinstance(url, str) or url.strip() == "":
            raise ValueError("url обязателен")
        _file_id, _s3_path, _src, text = await self._save_html_read_markdown(state, url.strip())
        return text
