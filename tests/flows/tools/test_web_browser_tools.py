from __future__ import annotations

import httpx2
import pytest

import apps.flows.src.services.mcp_client as mcp_client_mod
from apps.flows.src.models.mcp import MCPServerConfig
from apps.flows.src.services.browser_client import BrowserClient
from apps.flows.src.services.mcp_client import MCPClient, MCPClientError
from apps.flows.src.services.web_snapshot import _MCP_CALL_TIMEOUT_SECONDS
from apps.flows.src.state import ExecutionState
from apps.flows.tools.web.web_browser import (
    bound_browser_markdown,
    browser_duckduckgo_links,
    browser_duckduckgo_links_batch,
)
from core.types import require_json_object


def test_bounded_markdown_keeps_short_text_unchanged() -> None:
    markdown = "# Title\n\nShort page."

    bounded, truncated = bound_browser_markdown(markdown, 100)

    assert bounded == markdown
    assert truncated is False


def test_bounded_markdown_truncates_with_metadata() -> None:
    markdown = "x" * 240

    bounded, truncated = bound_browser_markdown(markdown, 120)

    assert truncated is True
    assert len(bounded) <= 120
    assert "markdown truncated" in bounded
    assert "original_chars=240" in bounded
    assert "max_markdown_chars=120" in bounded


def test_mcp_call_timeout_covers_browser_wait() -> None:
    # browser_wait ждёт до 60s — HTTP-таймаут MCP-вызова обязан быть больше,
    # иначе клиент рвёт соединение до ответа сервера (ASGI Closed + пустая ошибка).
    assert _MCP_CALL_TIMEOUT_SECONDS * 1000 > 60_000


class _TimeoutHttpClient:
    async def __aenter__(self) -> "_TimeoutHttpClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(self, *args: object, **kwargs: object) -> None:
        raise httpx2.ReadTimeout("")


@pytest.mark.asyncio
async def test_mcp_connection_error_includes_exception_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_client_mod,
        "get_httpx_client",
        lambda **_kwargs: _TimeoutHttpClient(),
    )
    client = MCPClient(
        MCPServerConfig(server_id="browser", name="Browser", url="http://browser:8009/mcp"),
        timeout=90.0,
    )
    client.protocol_version = "2025-11-25"

    with pytest.raises(MCPClientError, match="ReadTimeout"):
        _ = await client.call_tool("browser_wait", {"timeout_ms": 1})


@pytest.mark.asyncio
async def test_duckduckgo_links_returns_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
    state: ExecutionState,
) -> None:
    async def _fail(
        self: BrowserClient,
        _state: ExecutionState,
        _query: str,
        *,
        server_id: str = "browser",
        per_query_limit: int = 5,
    ) -> list[str]:
        raise MCPClientError("MCP connection error: ReadTimeout")

    monkeypatch.setattr(BrowserClient, "duckduckgo_links", _fail)

    result = require_json_object(
        await browser_duckduckgo_links.run({"query": "test"}, state),
        "browser_duckduckgo_links.result",
    )

    assert result["success"] is False
    assert result["urls"] == []
    assert "ReadTimeout" in str(result["error"])


@pytest.mark.asyncio
async def test_duckduckgo_links_returns_urls(
    monkeypatch: pytest.MonkeyPatch,
    state: ExecutionState,
) -> None:
    async def _ok(
        self: BrowserClient,
        _state: ExecutionState,
        _query: str,
        *,
        server_id: str = "browser",
        per_query_limit: int = 5,
    ) -> list[str]:
        return ["https://a.example", "https://b.example"]

    monkeypatch.setattr(BrowserClient, "duckduckgo_links", _ok)

    result = await browser_duckduckgo_links.run({"query": "test"}, state)

    assert result == {"success": True, "urls": ["https://a.example", "https://b.example"]}


@pytest.mark.asyncio
async def test_duckduckgo_links_batch_returns_structured_failure(
    monkeypatch: pytest.MonkeyPatch,
    state: ExecutionState,
) -> None:
    async def _fail(
        self: BrowserClient,
        _state: ExecutionState,
        _queries: list[str],
        *,
        server_id: str = "browser",
        per_query_limit: int = 5,
    ) -> list[str]:
        raise MCPClientError("MCP connection error: ReadTimeout")

    monkeypatch.setattr(BrowserClient, "duckduckgo_links_batch", _fail)

    result = require_json_object(
        await browser_duckduckgo_links_batch.run({"queries": ["a", "b"]}, state),
        "browser_duckduckgo_links_batch.result",
    )

    assert result["success"] is False
    assert result["urls"] == []
    assert "ReadTimeout" in str(result["error"])
