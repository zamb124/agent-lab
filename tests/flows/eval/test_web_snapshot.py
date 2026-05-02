"""Контракты Search / Describe и реализации web_snapshot."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from apps.flows.src.eval.web_snapshot import (
    BrowserSnapshotDescribe,
    Describe,
    DuckDuckGoBrowserSearch,
    Search,
)
from apps.flows.src.models.mcp import MCPCallResult
from core.files.reader.models import FileReadKind, FileReadResult, ReadPage


def test_search_describe_subclasses() -> None:
    assert issubclass(DuckDuckGoBrowserSearch, Search)
    assert issubclass(BrowserSnapshotDescribe, Describe)


@pytest.mark.asyncio
async def test_duckduckgo_links_returns_urls_from_snapshot() -> None:
    state: dict[str, object] = {}
    observe_count = 0

    async def fake_call_mcp_tool(
        server_id: str,
        tool_name: str,
        arguments: dict | None = None,
        *,
        state=None,
        timeout: float = 60.0,
    ) -> MCPCallResult:
        assert server_id == "user-browser"
        nonlocal observe_count
        if tool_name == "browser_create_session":
            payload: dict = {"session_id": "sess-1"}
        elif tool_name == "browser_navigate":
            payload = {}
        elif tool_name == "browser_observe":
            observe_count += 1
            if observe_count == 1:
                payload = {
                    "snapshot": {
                        "text": "control searchbox ref=@qbox extra",
                    },
                }
            else:
                payload = {
                    "snapshot": {
                        "text": "results https://example.org/article one",
                    },
                }
        elif tool_name in ("browser_fill", "browser_press", "browser_wait"):
            payload = {}
        elif tool_name == "browser_close_session":
            payload = {}
        else:
            raise AssertionError(f"unexpected tool {tool_name}")

        return MCPCallResult(
            is_error=False,
            content=[{"text": json.dumps(payload)}],
        )

    with patch("apps.flows.src.eval.web_snapshot.call_mcp_tool", side_effect=fake_call_mcp_tool):
        search = DuckDuckGoBrowserSearch()
        urls = await search.links(state, "hello world")

    assert urls == ["https://example.org/article"]


@pytest.mark.asyncio
async def test_duckduckgo_links_many_single_query_dedupes() -> None:
    state: dict[str, object] = {}
    observe_count = 0

    async def fake_call_mcp_tool(
        server_id: str,
        tool_name: str,
        arguments: dict | None = None,
        *,
        state=None,
        timeout: float = 60.0,
    ) -> MCPCallResult:
        nonlocal observe_count
        if tool_name == "browser_create_session":
            payload = {"session_id": "sess-x"}
        elif tool_name == "browser_navigate":
            payload = {}
        elif tool_name == "browser_observe":
            observe_count += 1
            if observe_count % 2 == 1:
                payload = {"snapshot": {"text": "textbox ref=@tb1"}}
            else:
                payload = {"snapshot": {"text": "https://a.example/x https://b.example/y"}}
        elif tool_name in ("browser_fill", "browser_press", "browser_wait", "browser_close_session"):
            payload = {}
        else:
            raise AssertionError(tool_name)

        return MCPCallResult(is_error=False, content=[{"text": json.dumps(payload)}])

    with patch("apps.flows.src.eval.web_snapshot.call_mcp_tool", side_effect=fake_call_mcp_tool):
        search = DuckDuckGoBrowserSearch(per_query_limit=10)
        urls = await search.links_many(state, ["q1"])

    assert "https://a.example/x" in urls
    assert "https://b.example/y" in urls


@pytest.mark.asyncio
async def test_browser_snapshot_describe_returns_markdown() -> None:
    state: dict[str, object] = {}

    async def fake_call_mcp_tool(
        server_id: str,
        tool_name: str,
        arguments: dict | None = None,
        *,
        state=None,
        timeout: float = 60.0,
    ) -> MCPCallResult:
        if tool_name == "browser_create_session":
            payload = {"session_id": "sess-c"}
        elif tool_name == "browser_navigate":
            payload = {}
        elif tool_name == "browser_save_html_to_s3":
            payload = {
                "file_id": "file_test_1",
                "s3_path": "s3://bucket/key",
                "source_url": "https://news.example/item",
            }
        elif tool_name == "browser_close_session":
            payload = {}
        else:
            raise AssertionError(tool_name)

        return MCPCallResult(is_error=False, content=[{"text": json.dumps(payload)}])

    read_result = FileReadResult(
        file_name="snapshot.html",
        detected_kind=FileReadKind.HTML,
        page_count=1,
        pages=[ReadPage(index=0, text="# Title\nbody")],
    )
    reader = AsyncMock()
    reader.read = AsyncMock(return_value=read_result)

    with patch("apps.flows.src.eval.web_snapshot.call_mcp_tool", side_effect=fake_call_mcp_tool):
        describe = BrowserSnapshotDescribe(file_reader=reader)
        md = await describe.page_markdown(state, "https://news.example/item")

    assert md == "# Title\nbody"
    reader.read.assert_awaited_once()
    call_kw = reader.read.await_args[0][0]
    assert call_kw["file_id"] == "file_test_1"
    assert call_kw["name"] == "snapshot.html"


@pytest.mark.asyncio
async def test_browser_snapshot_page_snapshot_returns_dict() -> None:
    state: dict[str, object] = {}

    async def fake_call_mcp_tool(
        server_id: str,
        tool_name: str,
        arguments: dict | None = None,
        *,
        state=None,
        timeout: float = 60.0,
    ) -> MCPCallResult:
        if tool_name == "browser_create_session":
            payload = {"session_id": "sess-snap"}
        elif tool_name == "browser_navigate":
            payload = {}
        elif tool_name == "browser_save_html_to_s3":
            payload = {
                "file_id": "fid_snap",
                "s3_path": "s3://b/k",
                "source_url": "https://x.example/p",
            }
        elif tool_name == "browser_close_session":
            payload = {}
        else:
            raise AssertionError(tool_name)

        return MCPCallResult(is_error=False, content=[{"text": json.dumps(payload)}])

    read_result = FileReadResult(
        file_name="snapshot.html",
        detected_kind=FileReadKind.HTML,
        page_count=1,
        pages=[ReadPage(index=0, text="body")],
    )
    reader = AsyncMock()
    reader.read = AsyncMock(return_value=read_result)

    with patch("apps.flows.src.eval.web_snapshot.call_mcp_tool", side_effect=fake_call_mcp_tool):
        describe = BrowserSnapshotDescribe(file_reader=reader)
        snap = await describe.page_snapshot(state, "https://x.example/p")

    assert snap["url"] == "https://x.example/p"
    assert snap["file_id"] == "fid_snap"
    assert snap["s3_path"] == "s3://b/k"
    assert snap["text"] == "body"


@pytest.mark.asyncio
async def test_duckduckgo_links_rejects_empty_query() -> None:
    s = DuckDuckGoBrowserSearch()
    with pytest.raises(ValueError, match="query"):
        await s.links({}, "  ")


@pytest.mark.asyncio
async def test_browser_snapshot_describe_rejects_empty_url() -> None:
    describe = BrowserSnapshotDescribe()
    with pytest.raises(ValueError, match="url"):
        await describe.page_markdown({}, "")
