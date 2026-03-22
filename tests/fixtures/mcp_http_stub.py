"""
Локальный HTTP-сервер с минимальным MCP JSON-RPC (initialize, tools/list, tools/call).

Используется вместо внешних endpoint в интеграционных тестах MCP: без сети и без
многосекундных таймаутов.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator

import pytest


class _MCPJsonRpcHandler(BaseHTTPRequestHandler):
    mcp_protocol_version = "2024-11-05"

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        req = json.loads(raw.decode("utf-8"))
        req_id = req.get("id")
        method = req.get("method")

        if method == "initialize":
            result = {
                "protocolVersion": self.mcp_protocol_version,
                "capabilities": {},
                "serverInfo": {"name": "stub-mcp", "version": "0.0.1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "stub_resolve_library",
                        "description": "Stub tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"libraryName": {"type": "string"}},
                        },
                    }
                ]
            }
        elif method == "tools/call":
            params = req.get("params") or {}
            tool_name = params.get("name", "")
            if tool_name != "stub_resolve_library":
                body = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": "Tool not found"},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                return
            result = {
                "content": [{"type": "text", "text": '{"ok": true}'}],
                "isError": False,
            }
        else:
            self.send_error(400, "unknown method")
            return

        body = json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if method == "initialize":
            self.send_header("Mcp-Session-Id", "stub-session-id")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


@pytest.fixture(scope="session")
def local_mcp_http_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _MCPJsonRpcHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.shutdown()
        thread.join(timeout=5)
