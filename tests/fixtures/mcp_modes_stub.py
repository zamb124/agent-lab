"""
Configurable local MCP stub: JSON vs SSE, session, tool results, HTTP/RPC errors.

Покрывает все режимы, которые реально поддерживает `MCPClient` (Streamable HTTP 2025-11-25).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Literal, override

import pytest

from core.types import JsonObject

MCP_STUB_PROTOCOL_VERSION = "2025-11-25"


@dataclass
class MCPStubRecordedRequest:
    method: str
    jsonrpc_method: str | None
    headers: dict[str, str]
    body: JsonObject


@dataclass
class MCPStubMode:
    """Профиль поведения локального MCP сервера."""

    response_format: Literal["json", "sse"] = "json"
    issue_session_id: bool = True
    http_status: int = 200
    tools: list[JsonObject] = field(default_factory=list)
    tool_call_result: JsonObject | None = None
    tool_call_rpc_error: JsonObject | None = None
    reject_missing_protocol_version: bool = True
    empty_jsonrpc_body: bool = False


@dataclass
class MCPStubState:
    mode: MCPStubMode
    recorded_requests: list[MCPStubRecordedRequest] = field(default_factory=list)


def default_stub_tools() -> list[JsonObject]:
    return [
        {
            "name": "stub_resolve_library",
            "description": "Stub tool",
            "inputSchema": {
                "type": "object",
                "properties": {"libraryName": {"type": "string"}},
            },
            "outputSchema": {
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
            },
            "annotations": {"readOnlyHint": True, "idempotentHint": True},
        }
    ]


def default_tool_call_success() -> JsonObject:
    return {
        "content": [{"type": "text", "text": '{"ok": true}'}],
        "isError": False,
    }


def _registry_handler_factory(state: MCPStubState) -> type[BaseHTTPRequestHandler]:
    class MCPModesStubHandler(BaseHTTPRequestHandler):
        stub_state: MCPStubState = state

        def _record(self, *, jsonrpc_method: str | None, body: JsonObject) -> None:
            headers = {key: value for key, value in self.headers.items()}
            self.stub_state.recorded_requests.append(
                MCPStubRecordedRequest(
                    method=self.command,
                    jsonrpc_method=jsonrpc_method,
                    headers=headers,
                    body=body,
                )
            )

        def _write_bytes(self, status: int, content_type: str, body: bytes, extra_headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if extra_headers is not None:
                for key, value in extra_headers.items():
                    self.send_header(key, value)
            self.end_headers()
            _ = self.wfile.write(body)

        def _write_jsonrpc(
            self,
            *,
            req_id: object,
            result: JsonObject | None = None,
            error: JsonObject | None = None,
            status: int = 200,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            envelope: JsonObject = {"jsonrpc": "2.0", "id": req_id}
            if error is not None:
                envelope["error"] = error
            else:
                envelope["result"] = result if result is not None else {}
            if self.stub_state.mode.response_format == "sse":
                payload = f"event: message\ndata: {json.dumps(envelope, separators=(',', ':'))}\n\n"
                self._write_bytes(status, "text/event-stream", payload.encode("utf-8"), extra_headers)
                return
            self._write_bytes(status, "application/json", json.dumps(envelope).encode("utf-8"), extra_headers)

        def do_POST(self) -> None:
            mode = self.stub_state.mode
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            req = json.loads(raw.decode("utf-8"))
            req_id = req.get("id")
            method = req.get("method")
            if not isinstance(method, str):
                self.send_error(400, "method required")
                return
            self._record(jsonrpc_method=method, body=req)

            if mode.empty_jsonrpc_body and method in ("tools/list", "tools/call"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                return

            if mode.http_status >= 400:
                self._write_bytes(mode.http_status, "application/json", b'{"error":"unauthorized"}')
                return

            if method == "initialize":
                result: JsonObject = {
                    "protocolVersion": MCP_STUB_PROTOCOL_VERSION,
                    "capabilities": {},
                    "serverInfo": {"name": "stub-mcp-modes", "version": "0.0.1"},
                }
                init_headers: dict[str, str] = {}
                if mode.issue_session_id:
                    init_headers["Mcp-Session-Id"] = "stub-session-id"
                self._write_jsonrpc(
                    req_id=req_id,
                    result=result,
                    extra_headers=init_headers,
                )
                return

            if method == "notifications/initialized":
                if mode.reject_missing_protocol_version:
                    protocol_header = self.headers.get("MCP-Protocol-Version")
                    if protocol_header != MCP_STUB_PROTOCOL_VERSION:
                        self.send_error(400, "missing MCP-Protocol-Version")
                        return
                self.send_response(202)
                self.end_headers()
                return

            if method in ("tools/list", "tools/call"):
                if mode.reject_missing_protocol_version:
                    protocol_header = self.headers.get("MCP-Protocol-Version")
                    if protocol_header != MCP_STUB_PROTOCOL_VERSION:
                        self.send_error(400, "missing MCP-Protocol-Version")
                        return

            if method == "tools/list":
                tools = mode.tools if mode.tools else default_stub_tools()
                self._write_jsonrpc(req_id=req_id, result={"tools": tools})
                return

            if method == "tools/call":
                if mode.tool_call_rpc_error is not None:
                    self._write_jsonrpc(req_id=req_id, error=mode.tool_call_rpc_error)
                    return
                params = req.get("params")
                if not isinstance(params, dict):
                    self.send_error(400, "params required")
                    return
                tool_name = params.get("name")
                if not isinstance(tool_name, str):
                    self.send_error(400, "tool name required")
                    return
                known_tools = {
                    tool["name"]
                    for tool in (mode.tools if mode.tools else default_stub_tools())
                    if isinstance(tool.get("name"), str)
                }
                if tool_name not in known_tools:
                    self._write_jsonrpc(
                        req_id=req_id,
                        error={"code": -32601, "message": "Tool not found"},
                    )
                    return
                result_payload = mode.tool_call_result if mode.tool_call_result is not None else default_tool_call_success()
                self._write_jsonrpc(req_id=req_id, result=result_payload)
                return

            self.send_error(400, "unknown method")

        @override
        def log_message(self, format: str, *args: object) -> None:
            return

    return MCPModesStubHandler


@pytest.fixture
def mcp_modes_stub() -> Iterator:
    """
    Фабрика локальных MCP stub-серверов.

    Usage:
        url, state = mcp_modes_stub(MCPStubMode(response_format="sse"))
    """
    servers: list[HTTPServer] = []

    def _start(mode: MCPStubMode | None = None) -> tuple[str, MCPStubState]:
        resolved_mode = mode if mode is not None else MCPStubMode(tools=default_stub_tools())
        state = MCPStubState(mode=resolved_mode)
        handler_cls = _registry_handler_factory(state)
        server = HTTPServer(("127.0.0.1", 0), handler_cls)
        servers.append(server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        return f"http://127.0.0.1:{port}/mcp", state

    yield _start

    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture(scope="session")
def local_mcp_http_url(mcp_modes_stub_session: str) -> str:
    """Session-scoped JSON MCP stub для legacy-тестов."""
    return mcp_modes_stub_session


@pytest.fixture(scope="session")
def mcp_modes_stub_session() -> Iterator[str]:
    """Session-scoped default JSON MCP stub для существующих тестов."""
    state = MCPStubState(mode=MCPStubMode(tools=default_stub_tools()))
    handler_cls = _registry_handler_factory(state)
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.shutdown()
        server.server_close()
