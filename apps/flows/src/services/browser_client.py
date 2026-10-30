"""BrowserClient — DuckDuckGo search + page snapshot for browser_* tools."""

from __future__ import annotations

from apps.flows.src.services.web_snapshot import BrowserSnapshotDescribe, DuckDuckGoBrowserSearch
from apps.flows.src.state import ExecutionState
from core.types import JsonObject


class BrowserClient:
    """Поиск ссылок и снимок страницы через MCP browser."""

    async def duckduckgo_links(
        self,
        state: ExecutionState,
        query: str,
        *,
        server_id: str = "browser",
        per_query_limit: int = 5,
    ) -> list[str]:
        search = DuckDuckGoBrowserSearch(server_id=server_id, per_query_limit=per_query_limit)
        return await search.links(state, query)

    async def duckduckgo_links_batch(
        self,
        state: ExecutionState,
        queries: list[str],
        *,
        server_id: str = "browser",
        per_query_limit: int = 5,
    ) -> list[str]:
        search = DuckDuckGoBrowserSearch(server_id=server_id, per_query_limit=per_query_limit)
        return await search.links_many(state, queries)

    async def page_markdown(
        self,
        state: ExecutionState,
        url: str,
        *,
        server_id: str = "browser",
        navigation_timeout_ms: int = 30000,
        ingest_source: str = "simple_crawler",
    ) -> str:
        describe = BrowserSnapshotDescribe(
            server_id=server_id,
            navigation_timeout_ms=navigation_timeout_ms,
            ingest_source=ingest_source,
        )
        return await describe.page_markdown(state, url)

    async def page_snapshot(
        self,
        state: ExecutionState,
        url: str,
        *,
        server_id: str = "browser",
        navigation_timeout_ms: int = 30000,
        ingest_source: str = "simple_crawler",
    ) -> JsonObject:
        describe = BrowserSnapshotDescribe(
            server_id=server_id,
            navigation_timeout_ms=navigation_timeout_ms,
            ingest_source=ingest_source,
        )
        snap = await describe.page_snapshot(state, url)
        return {
            "url": snap["url"],
            "file_id": snap["file_id"],
            "s3_path": snap["s3_path"],
            "text": snap["text"],
        }
