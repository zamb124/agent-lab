"""
Strict integration tests: все режимы MCP transport/runtime.

Покрывает реальные ветки `MCPClient` и API sync/test без mocks:
- JSON vs SSE (Streamable HTTP)
- session / no-session
- multi-tool discovery
- tool call: success, isError, structuredContent, RPC error
- HTTP 401 / empty body
- custom headers и @var: resolution
- catalog crawl: streamable-http vs sse remote types
"""

from __future__ import annotations

import pytest

from apps.flows.src.clients.mcp_client import MCPClient, MCPClientError
from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.models.mcp import MCPServerConfig, MCPTransportType
from apps.flows.src.models.mcp_catalog import MCPCatalogVerifyStatus
from apps.flows.src.services.mcp_catalog_crawler import crawl_mcp_registry
from apps.flows.src.services.mcp_catalog_ids import (
    catalog_id_from_registry_name,
    server_id_from_catalog_id,
)
from apps.flows.src.services.mcp_catalog_provisioner import provision_mcp_catalog_for_company
from apps.flows.src.services.mcp_sync import sync_mcp_server_tools
from core.integrations.mcp import MCP_PROTOCOL_VERSION, MCPToolDefinition
from tests.fixtures.mcp_modes_stub import (
    MCPStubMode,
    default_stub_tools,
)
from tests.fixtures.mcp_registry_stub import build_registry_server_item
from tests.flows.integration.mcp_catalog_helpers import (
    build_verified_catalog_entry,
    cleanup_catalog_and_server,
    mcp_catalog_settings,
    persist_catalog_entry,
)


def _server_config(*, url: str, server_id: str, transport_type: MCPTransportType = MCPTransportType.HTTP) -> MCPServerConfig:
    return MCPServerConfig(
        server_id=server_id,
        name=f"MCP mode test {server_id}",
        url=url,
        transport_type=transport_type,
        headers={},
        is_active=True,
    )


@pytest.mark.asyncio
async def test_mcp_json_response_initialize_list_and_call(mcp_modes_stub, unique_id: str) -> None:
    """Базовый режим: application/json на initialize/tools/list/tools/call."""
    url, state = mcp_modes_stub(MCPStubMode(tools=default_stub_tools()))
    client = MCPClient(_server_config(url=url, server_id=f"json_{unique_id}"), timeout=10.0)

    init = await client.initialize()
    assert init.protocol_version == MCP_PROTOCOL_VERSION
    assert client.session_id == "stub-session-id"

    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0].tool_name == "stub_resolve_library"

    result = await client.call_tool("stub_resolve_library", {"libraryName": "lit"})
    assert result.is_error is False
    assert result.get_text() == '{"ok": true}'

    rpc_methods = [item.jsonrpc_method for item in state.recorded_requests if item.jsonrpc_method]
    assert rpc_methods[0] == "initialize"
    assert "tools/list" in rpc_methods
    assert "tools/call" in rpc_methods
    assert state.recorded_requests[0].headers.get("Accept") == "application/json, text/event-stream"


@pytest.mark.asyncio
async def test_mcp_sse_response_initialize_list_and_call(mcp_modes_stub, unique_id: str) -> None:
    """Streamable HTTP: сервер отвечает text/event-stream с data: JSON-RPC envelope."""
    url, _state = mcp_modes_stub(
        MCPStubMode(response_format="sse", tools=default_stub_tools())
    )
    client = MCPClient(_server_config(url=url, server_id=f"sse_{unique_id}"), timeout=10.0)

    _ = await client.initialize()
    tools = await client.list_tools()
    assert len(tools) == 1

    result = await client.call_tool("stub_resolve_library", {"libraryName": "react"})
    assert result.is_error is False
    assert '{"ok": true}' in result.get_text()


@pytest.mark.asyncio
async def test_mcp_works_without_session_id_header(mcp_modes_stub, unique_id: str) -> None:
    """Некоторые MCP не выдают Mcp-Session-Id — клиент продолжает работу."""
    url, _state = mcp_modes_stub(
        MCPStubMode(issue_session_id=False, tools=default_stub_tools())
    )
    client = MCPClient(_server_config(url=url, server_id=f"nosess_{unique_id}"), timeout=10.0)

    _ = await client.initialize()
    assert client.session_id is None
    tools = await client.list_tools()
    assert len(tools) == 1


@pytest.mark.asyncio
async def test_mcp_sse_sync_api_end_to_end(client, mcp_modes_stub, unique_id: str) -> None:
    """API sync/test работает когда upstream отвечает SSE."""
    url, _state = mcp_modes_stub(
        MCPStubMode(response_format="sse", tools=default_stub_tools())
    )
    server_id = f"sse_api_{unique_id}"
    create_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": server_id,
            "name": "SSE MCP",
            "url": url,
            "transport_type": "sse",
        },
    )
    assert create_response.status_code == 200, create_response.text
    assert create_response.json()["transport_type"] == "sse"

    sync_response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
    assert sync_response.status_code == 200, sync_response.text
    sync_body = sync_response.json()
    assert sync_body["success"] is True
    assert sync_body["tools_count"] == 1
    assert sync_body["tools"][0]["name"] == "stub_resolve_library"

    test_response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/test")
    assert test_response.status_code == 200
    assert test_response.json()["tools_count"] == 1

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_mcp_multi_tool_discovery_and_sync(client, mcp_modes_stub, unique_id: str) -> None:
    """tools/list с несколькими tools → все попадают в tool_repository."""
    tools_payload = [
        {
            "name": "alpha_tool",
            "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
        },
        {
            "name": "beta-tool",
            "inputSchema": {"type": "object", "properties": {"n": {"type": "integer"}}},
        },
    ]
    url, _state = mcp_modes_stub(MCPStubMode(tools=tools_payload))
    server_id = f"multi_{unique_id}"
    _ = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": server_id,
            "name": "Multi tool MCP",
            "url": url,
            "transport_type": "http",
        },
    )
    sync_response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
    assert sync_response.status_code == 200
    names = sorted(tool["name"] for tool in sync_response.json()["tools"])
    assert names == ["alpha_tool", "beta-tool"]

    tools_response = await client.get("/flows/api/v1/tools/all")
    mcp_tools = [
        tool for tool in tools_response.json()["items"] if tool.get("mcp_server_id") == server_id
    ]
    assert len(mcp_tools) == 2

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_mcp_tool_call_is_error_result(mcp_modes_stub, unique_id: str) -> None:
    """tools/call может вернуть isError=true без JSON-RPC error."""
    url, _state = mcp_modes_stub(
        MCPStubMode(
            tools=default_stub_tools(),
            tool_call_result={
                "content": [{"type": "text", "text": "business failure"}],
                "isError": True,
            },
        )
    )
    client = MCPClient(_server_config(url=url, server_id=f"iserr_{unique_id}"), timeout=10.0)
    result = await client.call_tool("stub_resolve_library", {"libraryName": "x"})
    assert result.is_error is True
    assert result.get_text() == "business failure"


@pytest.mark.asyncio
async def test_mcp_tool_call_structured_content(mcp_modes_stub, unique_id: str) -> None:
    """MCP 2025-11-25 structuredContent парсится в MCPCallResult."""
    url, _state = mcp_modes_stub(
        MCPStubMode(
            tools=default_stub_tools(),
            tool_call_result={
                "content": [],
                "structuredContent": {"providers": {"x": {"status": "ok"}}},
                "isError": False,
            },
        )
    )
    client = MCPClient(_server_config(url=url, server_id=f"struct_{unique_id}"), timeout=10.0)
    result = await client.call_tool("stub_resolve_library", {"libraryName": "x"})
    assert result.is_error is False
    assert result.structured_content == {"providers": {"x": {"status": "ok"}}}


@pytest.mark.asyncio
async def test_mcp_tool_call_rpc_error_envelope(mcp_modes_stub, unique_id: str) -> None:
    """JSON-RPC error envelope → MCPClientError."""
    url, _state = mcp_modes_stub(
        MCPStubMode(
            tools=default_stub_tools(),
            tool_call_rpc_error={"code": -32000, "message": "upstream failed"},
        )
    )
    client = MCPClient(_server_config(url=url, server_id=f"rpcerr_{unique_id}"), timeout=10.0)
    with pytest.raises(MCPClientError, match="upstream failed"):
        _ = await client.call_tool("stub_resolve_library", {"libraryName": "x"})


@pytest.mark.asyncio
async def test_mcp_http_401_fails_closed(client, mcp_modes_stub, unique_id: str) -> None:
    """HTTP 401 на MCP endpoint → ошибка sync (без silent fallback)."""
    url, _state = mcp_modes_stub(MCPStubMode(http_status=401, tools=default_stub_tools()))
    server_id = f"http401_{unique_id}"
    _ = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": server_id,
            "name": "401 MCP",
            "url": url,
            "transport_type": "http",
        },
    )
    sync_response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
    assert sync_response.status_code >= 400
    _ = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")



@pytest.mark.asyncio
async def test_mcp_catalog_provision_includes_auth_required_entries(
    client,
    local_mcp_http_url: str,
    unique_id: str,
) -> None:
    """Catalog verify_status=auth_required всё ещё provisionable (needs credentials at runtime)."""
    catalog_id = f"authreq_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=local_mcp_http_url,
        verify_status=MCPCatalogVerifyStatus.AUTH_REQUIRED,
    )
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(container=container)

    assert stats.added == 1
    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_mcp_custom_headers_reach_upstream(mcp_modes_stub, unique_id: str) -> None:
    """Custom headers из MCPServerConfig реально уходят в HTTP запрос."""
    url, state = mcp_modes_stub(MCPStubMode(tools=default_stub_tools()))
    config = MCPServerConfig(
        server_id=f"hdr_{unique_id}",
        name="Headers",
        url=url,
        transport_type=MCPTransportType.HTTP,
        headers={"X-Custom-Probe": "probe-value"},
        is_active=True,
    )
    client = MCPClient(config, timeout=10.0)
    _ = await client.initialize()
    initialize_request = state.recorded_requests[0]
    assert initialize_request.headers.get("X-Custom-Probe") == "probe-value"


@pytest.mark.asyncio
async def test_mcp_empty_response_body_raises(mcp_modes_stub, unique_id: str) -> None:
    """Пустое тело HTTP-ответа на tools/list → MCPClientError."""
    url, _state = mcp_modes_stub(
        MCPStubMode(tools=default_stub_tools(), empty_jsonrpc_body=True)
    )
    client = MCPClient(_server_config(url=url, server_id=f"empty_{unique_id}"), timeout=10.0)
    with pytest.raises(MCPClientError, match="empty response"):
        _ = await client.list_tools()


@pytest.mark.asyncio
async def test_mcp_catalog_crawl_maps_streamable_http_to_http_transport(
    local_mcp_registry_stub,
    mcp_modes_stub,
    unique_id: str,
) -> None:
    """Registry remote type `streamable-http` → catalog.transport_type=http."""
    url, _state = mcp_modes_stub(MCPStubMode(tools=default_stub_tools()))
    registry_base_url, state = local_mcp_registry_stub
    registry_name = f"test.local/stream_{unique_id}"
    catalog_id = catalog_id_from_registry_name(registry_name)
    state.pages = [
        {
            "servers": [
                build_registry_server_item(
                    registry_name=registry_name,
                    upstream_url=url.replace("http://", "https://"),
                    remote_type="streamable-http",
                )
            ],
            "metadata": {},
        }
    ]
    container = as_flow_runtime_container(get_container())
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        max_verify_per_crawl=0,
        auto_provision="disabled",
    ):
        _ = await crawl_mcp_registry(container=container)

    entry = await container.mcp_catalog_repository.get(catalog_id)
    assert entry is not None
    assert entry.transport_type == "http"

    _ = await container.mcp_catalog_repository.delete(catalog_id)


@pytest.mark.asyncio
async def test_mcp_tool_not_found_rpc_error(mcp_modes_stub, unique_id: str) -> None:
    """Вызов неизвестного tool → JSON-RPC error от upstream."""
    url, _state = mcp_modes_stub(MCPStubMode(tools=default_stub_tools()))
    client = MCPClient(_server_config(url=url, server_id=f"notfound_{unique_id}"), timeout=10.0)
    with pytest.raises(MCPClientError, match="Tool not found"):
        _ = await client.call_tool("missing_tool", {})


@pytest.mark.asyncio
async def test_mcp_secret_var_resolved_in_headers(client, mcp_modes_stub, unique_id: str, app) -> None:
    """Secret @var: резолвится в реальное значение при sync (не маска ***)."""
    from apps.flows.src.container import get_container
    from tests.fixtures.variables_helpers import upsert_static_variable_via_service

    url, state = mcp_modes_stub(MCPStubMode(tools=default_stub_tools()))
    server_id = f"secvar_{unique_id}"
    variable_key = f"mcp_secret_hdr_{unique_id}"
    container = get_container()
    await upsert_static_variable_via_service(
        container,
        variable_key,
        "super-secret-token",
        secret=True,
        shared_for_execution=True,
    )

    create_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": server_id,
            "name": "Secret var headers",
            "url": url,
            "transport_type": "http",
            "headers": {"Authorization": f"Bearer @var:{variable_key}"},
        },
    )
    assert create_response.status_code == 200

    sync_response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
    assert sync_response.status_code == 200, sync_response.text

    initialize_requests = [
        item for item in state.recorded_requests if item.jsonrpc_method == "initialize"
    ]
    assert initialize_requests[-1].headers.get("Authorization") == "Bearer super-secret-token"

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_mcp_var_in_headers_resolved_before_request(client, mcp_modes_stub, unique_id: str, app) -> None:
    """@var: в headers резолвится через variables_service при sync."""
    from apps.flows.src.container import get_container
    from tests.fixtures.variables_helpers import upsert_static_variable_via_service

    url, state = mcp_modes_stub(MCPStubMode(tools=default_stub_tools()))
    server_id = f"varhdr_{unique_id}"
    variable_key = f"mcp_hdr_token_{unique_id}"
    container = get_container()
    await upsert_static_variable_via_service(
        container,
        variable_key,
        "resolved-secret",
        secret=True,
        shared_for_execution=True,
    )

    create_response = await client.post(
        "/flows/api/v1/mcp/servers",
        json={
            "server_id": server_id,
            "name": "Var headers",
            "url": url,
            "transport_type": "http",
            "headers": {"Authorization": f"Bearer @var:{variable_key}"},
        },
    )
    assert create_response.status_code == 200

    sync_response = await client.post(f"/flows/api/v1/mcp/servers/{server_id}/sync")
    assert sync_response.status_code == 200, sync_response.text

    initialize_requests = [
        item for item in state.recorded_requests if item.jsonrpc_method == "initialize"
    ]
    assert len(initialize_requests) >= 1
    assert initialize_requests[-1].headers.get("Authorization") == "Bearer resolved-secret"

    _ = await client.delete(f"/flows/api/v1/mcp/servers/{server_id}")


@pytest.mark.asyncio
async def test_mcp_catalog_crawl_maps_sse_remote_to_sse_transport(
    local_mcp_registry_stub,
    mcp_modes_stub,
    unique_id: str,
) -> None:
    """Registry remote type `sse` → catalog.transport_type=sse."""
    url, _state = mcp_modes_stub(MCPStubMode(response_format="sse", tools=default_stub_tools()))
    registry_base_url, state = local_mcp_registry_stub
    registry_name = f"test.local/sse_{unique_id}"
    catalog_id = catalog_id_from_registry_name(registry_name)
    state.pages = [
        {
            "servers": [
                build_registry_server_item(
                    registry_name=registry_name,
                    upstream_url=url.replace("http://", "https://"),
                    remote_type="sse",
                )
            ],
            "metadata": {},
        }
    ]
    container = as_flow_runtime_container(get_container())
    with mcp_catalog_settings(
        registry_base_url=registry_base_url,
        max_verify_per_crawl=0,
        auto_provision="disabled",
    ):
        _ = await crawl_mcp_registry(container=container)

    entry = await container.mcp_catalog_repository.get(catalog_id)
    assert entry is not None
    assert entry.transport_type == "sse"

    verified = entry.model_copy(
        update={
            "upstream_url": url,
            "verify_status": MCPCatalogVerifyStatus.VERIFIED,
            "tool_count_snapshot": 1,
        }
    )
    verified.catalog_snapshot_hash = verified.recompute_snapshot_hash()
    _ = await persist_catalog_entry(container=container, entry=verified)

    _ = await container.mcp_catalog_repository.delete(catalog_id)


@pytest.mark.asyncio
async def test_mcp_catalog_provision_sse_transport_syncs_via_sse_upstream(
    client,
    mcp_modes_stub,
    unique_id: str,
) -> None:
    """Catalog entry transport_type=sse + SSE upstream → provision + sync."""
    url, _state = mcp_modes_stub(
        MCPStubMode(response_format="sse", tools=default_stub_tools())
    )
    catalog_id = f"sse_cat_{unique_id}"
    server_id = server_id_from_catalog_id(catalog_id)
    container = as_flow_runtime_container(get_container())
    entry = build_verified_catalog_entry(
        catalog_id=catalog_id,
        upstream_url=url,
        transport_type="sse",
    )
    _ = await persist_catalog_entry(container=container, entry=entry)

    with mcp_catalog_settings(auto_provision="all_verified"):
        stats = await provision_mcp_catalog_for_company(container=container)
    assert stats.added == 1

    get_response = await client.get(f"/flows/api/v1/mcp/servers/{server_id}")
    assert get_response.status_code == 200
    assert get_response.json()["transport_type"] == "sse"
    assert len(get_response.json()["cached_tools"]) == 1

    await cleanup_catalog_and_server(
        container=container,
        client=client,
        catalog_id=catalog_id,
        server_id=server_id,
    )


@pytest.mark.asyncio
async def test_mcp_wire_tool_meta_and_output_schema(mcp_modes_stub, unique_id: str) -> None:
    """Wire tool с outputSchema/annotations/meta → MCPDiscoveredTool."""
    wire_tool: dict[str, object] = {
        "name": "meta_tool",
        "title": "Meta Tool",
        "description": "Has meta",
        "inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "outputSchema": {"type": "object", "properties": {"answer": {"type": "string"}}},
        "annotations": {"readOnlyHint": True},
        "_meta": {"source": "stub"},
    }
    url, _state = mcp_modes_stub(MCPStubMode(tools=[wire_tool]))
    container = as_flow_runtime_container(get_container())
    server = _server_config(url=url, server_id=f"meta_{unique_id}")
    _ = await container.mcp_server_repository.set(server)
    tool_ids, tools = await sync_mcp_server_tools(container=container, server_config=server)
    assert len(tool_ids) == 1
    discovered = tools[0]
    assert discovered.tool_name == "meta_tool"
    assert discovered.title == "Meta Tool"
    assert discovered.output_schema == {"type": "object", "properties": {"answer": {"type": "string"}}}
    assert discovered.annotations == {"readOnlyHint": True}
    assert discovered.meta == {"source": "stub"}

    _ = await container.mcp_server_repository.delete(server.server_id)


def test_mcp_jsonrpc_body_parse_multiline_sse_and_done() -> None:
    """Парсер принимает SSE с несколькими data: строками и игнорирует [DONE]."""
    text = (
        "event: message\n"
        'data: {"noise": true}\n\n'
        'data: {"jsonrpc":"2.0","id":3,"result":{"tools":[]}}\n\n'
        "data: [DONE]\n\n"
    )
    envelope = MCPClient._jsonrpc_envelope_from_body(text)
    assert envelope is not None
    assert envelope.get("id") == 3
    assert envelope.get("result") == {"tools": []}


def test_mcp_wire_tool_rejects_platform_aliases() -> None:
    """Wire contract: только MCP camelCase поля."""
    with pytest.raises(ValueError, match="inputSchema"):
        _ = MCPToolDefinition.from_wire(
            {
                "name": "bad",
                "parameters_schema": {"type": "object", "properties": {}},
            }
        )
