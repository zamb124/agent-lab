"""Платформенные @tool для браузера (web_browser)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from apps.flows.src.eval.web_snapshot import DuckDuckGoBrowserSearch
from apps.flows.src.models.mcp import MCPCallResult
from apps.flows.tools.web_browser import (
    browser_duckduckgo_links,
    browser_duckduckgo_links_batch,
    browser_page_markdown,
    browser_page_snapshot,
)
from core.state import ExecutionState


def _minimal_state() -> ExecutionState:
    return ExecutionState(
        task_id="t-web-tools",
        context_id="c-web-tools",
        user_id="u-web-tools",
        session_id="agent:c-web-tools",
    )


@pytest.mark.asyncio
async def test_browser_duckduckgo_links_run_returns_urls() -> None:
    state = _minimal_state()
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
            payload: dict = {"session_id": "sess-tool-1"}
        elif tool_name == "browser_navigate":
            payload = {}
        elif tool_name == "browser_observe":
            observe_count += 1
            if observe_count == 1:
                payload = {"snapshot": {"text": "control searchbox ref=@q1"}}
            else:
                payload = {"snapshot": {"text": "hit https://tool.example/doc end"}}
        elif tool_name in ("browser_fill", "browser_press", "browser_wait"):
            payload = {}
        elif tool_name == "browser_close_session":
            payload = {}
        else:
            raise AssertionError(tool_name)

        return MCPCallResult(is_error=False, content=[{"text": json.dumps(payload)}])

    with patch("apps.flows.src.eval.web_snapshot.call_mcp_tool", side_effect=fake_call_mcp_tool):
        out = await browser_duckduckgo_links.run(
            {"query": "q tool", "server_id": "browser", "per_query_limit": 5},
            state,
        )

    assert out["success"] is True
    assert out["urls"] == ["https://tool.example/doc"]


@pytest.mark.asyncio
async def test_browser_duckduckgo_links_batch_run_delegates_to_links_many() -> None:
    state = _minimal_state()
    with patch.object(
        DuckDuckGoBrowserSearch,
        "links_many",
        new_callable=AsyncMock,
        return_value=["https://dup.example/x", "https://other.example/y"],
    ) as links_many:
        out = await browser_duckduckgo_links_batch.run(
            {"queries": ["a", "b"], "per_query_limit": 10},
            state,
        )

    links_many.assert_awaited_once()
    assert links_many.await_args.args[0] is state
    assert links_many.await_args.args[1] == ["a", "b"]
    assert out["success"] is True
    assert out["urls"] == ["https://dup.example/x", "https://other.example/y"]


@pytest.mark.asyncio
async def test_browser_page_markdown_run_uses_describe() -> None:
    state = _minimal_state()
    with patch("apps.flows.tools.web_browser.BrowserSnapshotDescribe") as mock_cls:
        instance = mock_cls.return_value
        instance.page_markdown = AsyncMock(return_value="# Md\nok")
        out = await browser_page_markdown.run({"url": "https://md.example/p"}, state)

    mock_cls.assert_called_once()
    _call_kw = mock_cls.call_args.kwargs
    assert _call_kw["server_id"] == "browser"
    assert _call_kw["navigation_timeout_ms"] == 30000
    assert _call_kw["ingest_source"] == "simple_crawler"
    instance.page_markdown.assert_awaited_once()
    assert out == {"success": True, "markdown": "# Md\nok"}


@pytest.mark.asyncio
async def test_browser_page_snapshot_run_uses_describe() -> None:
    state = _minimal_state()
    snap = {
        "url": "https://snap.example/u",
        "file_id": "fid1",
        "s3_path": "s3://x/y",
        "text": "body",
    }
    with patch("apps.flows.tools.web_browser.BrowserSnapshotDescribe") as mock_cls:
        instance = mock_cls.return_value
        instance.page_snapshot = AsyncMock(return_value=snap)
        out = await browser_page_snapshot.run({"url": "https://snap.example/u"}, state)

    assert out == {"success": True, **snap}


@pytest.mark.asyncio
async def test_browser_duckduckgo_links_run_maps_value_error_to_payload() -> None:
    state = _minimal_state()
    with patch(
        "apps.flows.tools.web_browser.DuckDuckGoBrowserSearch.links",
        new_callable=AsyncMock,
        side_effect=ValueError("query обязателен"),
    ):
        out = await browser_duckduckgo_links.run({"query": "x"}, state)

    assert out["success"] is False
    assert "query" in out["error"]
