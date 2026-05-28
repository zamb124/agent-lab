import pytest
from httpx import ASGITransport, AsyncClient

from apps.search.api.mcp import _tools
from apps.search.config import SearchIntegrationConfig
from apps.search.main import app
from apps.search.services import MetaSearchService
from core.integrations.mcp import MCP_PROTOCOL_VERSION
from core.search import MetaSearchRequest


def test_search_mcp_exposes_search_tools() -> None:
    tools = _tools()

    assert [tool.name for tool in tools] == [
        "meta_web_search",
        "search_suggest",
        "search_result_insights",
    ]
    for tool in tools:
        assert tool.parameters_schema["type"] == "object"
        assert tool.output_schema is not None
        assert tool.output_schema["type"] == "object"


@pytest.mark.asyncio
async def test_meta_search_reports_missing_serper_key(provider_state_store) -> None:
    response = await MetaSearchService(SearchIntegrationConfig(), provider_state_store).search(
        MetaSearchRequest(query="humanitec", providers=["serper"])
    )

    assert response.results == []
    assert response.providers["serper"].ok is False
    assert response.providers["serper"].error == "serper api key is not configured"


async def _post_mcp(client: AsyncClient, payload: dict[str, object], *, protocol_header: bool = True):
    headers = {}
    if protocol_header:
        headers["MCP-Protocol-Version"] = MCP_PROTOCOL_VERSION
    return await client.post("/search/api/v1/mcp", json=payload, headers=headers)


@pytest.mark.asyncio
async def test_search_mcp_jsonrpc_endpoint_contract() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://search") as client:
        initialize = await client.post(
            "/search/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert initialize.status_code == 200
        assert initialize.headers.get("Mcp-Session-Id")
        assert initialize.json()["result"]["serverInfo"]["name"] == "platform-search"

        missing_header = await client.post(
            "/search/api/v1/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert missing_header.status_code == 400
        assert missing_header.json()["error"]["message"] == "MCP-Protocol-Version header is required"

        initialized = await _post_mcp(
            client,
            {"jsonrpc": "2.0", "id": 3, "method": "notifications/initialized"},
        )
        assert initialized.status_code == 202
        assert initialized.json() == {}

        tools = await _post_mcp(client, {"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        assert tools.status_code == 200
        assert tools.json()["result"]["tools"][0]["name"] == "meta_web_search"
        assert tools.json()["result"]["tools"][1]["name"] == "search_suggest"
        assert tools.json()["result"]["tools"][2]["name"] == "search_result_insights"

        missing_name = await _post_mcp(
            client,
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {}},
        )
        assert missing_name.json()["error"]["message"] == "tools/call: params.name is required"

        bad_arguments = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "meta_web_search", "arguments": []},
            },
        )
        assert bad_arguments.json()["error"]["message"] == "tools/call: params.arguments must be object"

        default_arguments = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "meta_web_search"},
            },
        )
        assert "Field required" in default_arguments.json()["error"]["message"]

        unknown_tool = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "unknown", "arguments": {"query": "humanitec"}},
            },
        )
        assert "Tool not found: unknown" in unknown_tool.json()["error"]["message"]

        call = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "meta_web_search",
                    "arguments": {"query": "humanitec", "providers": ["unsupported"]},
                },
            },
        )
        payload = call.json()["result"]
        assert payload["structuredContent"]["providers"]["unsupported"]["error"] == (
            "unsupported search provider: unsupported"
        )
        assert payload["isError"] is False
        assert payload["content"][0]["type"] == "text"

        result = {
            "title": "Humanitec Search",
            "url": "https://example.com/search",
            "snippet": "Humanitec search platform",
            "display_url": "example.com",
            "provider": "serper",
            "provider_rank": 1,
            "rank": 1,
            "score": 1.0,
            "published_at": None,
            "source_type": "organic",
        }
        suggestions = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "search_suggest",
                    "arguments": {
                        "query": "Humanitec Search",
                        "results": [result],
                        "mode": "research",
                        "limit": 4,
                    },
                },
            },
        )
        assert suggestions.json()["result"]["structuredContent"]["mode"] == "research"
        assert suggestions.json()["result"]["structuredContent"]["suggestions"]

        insights = await _post_mcp(
            client,
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "search_result_insights",
                    "arguments": {
                        "query": "Humanitec Search",
                        "results": [result],
                        "mode": "deep",
                    },
                },
            },
        )
        insight_payload = insights.json()["result"]["structuredContent"]
        assert insight_payload["insights"][0]["actions"] == [
            "open_source",
            "summarize_source",
            "ask_source",
            "extract_facts",
        ]

        unknown_method = await _post_mcp(
            client,
            {"jsonrpc": "2.0", "id": 12, "method": "unknown/method"},
        )
        assert unknown_method.json()["error"]["message"] == "Method not found: unknown/method"
