"""
Локальный HTTP stub Official MCP Registry API (`GET /v0/servers`).

Без внешней сети: тесты crawl парсят реальный JSON так же, как production crawler.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import override
from urllib.parse import parse_qs, urlparse

import pytest

from core.types import JsonObject


@dataclass
class MCPRegistryStubState:
    """Состояние stub registry: страницы ответа API."""

    pages: list[JsonObject] = field(default_factory=list)


def _registry_handler_factory(state: MCPRegistryStubState) -> type[BaseHTTPRequestHandler]:
    class MCPRegistryStubHandler(BaseHTTPRequestHandler):
        registry_state: MCPRegistryStubState = state

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/v0/servers":
                self.send_error(404, "not found")
                return
            query = parse_qs(parsed.query)
            cursor_values = query.get("cursor")
            cursor = cursor_values[0] if cursor_values else None
            page_index = 0
            if cursor is not None:
                if not cursor.isdigit():
                    self.send_error(400, "invalid cursor")
                    return
                page_index = int(cursor)
            if page_index >= len(self.registry_state.pages):
                payload: JsonObject = {"servers": [], "metadata": {}}
            else:
                payload = self.registry_state.pages[page_index]
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            _ = self.wfile.write(body)

        @override
        def log_message(self, format: str, *args: object) -> None:
            return

    return MCPRegistryStubHandler


def build_registry_server_item(
    *,
    registry_name: str,
    upstream_url: str,
    title: str | None = None,
    description: str | None = None,
    remote_type: str = "streamable-http",
    is_latest: bool = True,
) -> JsonObject:
    """Один элемент `servers[]` в формате registry API."""
    server_payload: JsonObject = {
        "name": registry_name,
        "title": title if title is not None else registry_name,
        "version": "1.0.0",
        "remotes": [{"type": remote_type, "url": upstream_url}],
    }
    if description is not None:
        server_payload["description"] = description
    item: JsonObject = {"server": server_payload}
    if is_latest:
        item["_meta"] = {
            "io.modelcontextprotocol.registry/official": {"isLatest": True},
        }
    return item


@pytest.fixture
def local_mcp_registry_stub() -> Iterator[tuple[str, MCPRegistryStubState]]:
    """Запускает локальный registry stub; возвращает `(base_url, state)`."""
    state = MCPRegistryStubState(pages=[{"servers": [], "metadata": {}}])
    handler_cls = _registry_handler_factory(state)
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", state
    finally:
        server.shutdown()
        thread.join(timeout=5)
