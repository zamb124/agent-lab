"""
WebSocket helpers для HumanitecAgent tunnel E2E.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

FRONTEND_WS_BASE = "ws://127.0.0.1:9004"
AGENT_TUNNEL_WS_PATH = "/frontend/api/agent/tunnel"


@asynccontextmanager
async def connect_agent_tunnel_ws(device_token: str) -> AsyncIterator[Any]:
    import websockets

    ws_uri = f"{FRONTEND_WS_BASE}{AGENT_TUNNEL_WS_PATH}?token={device_token}"
    async with websockets.connect(ws_uri) as websocket:
        yield websocket


async def expect_tunnel_rejected(
    ws_uri: str,
    *,
    expected_codes: set[int] | None = None,
) -> int:
    import websockets

    allowed_codes = expected_codes if expected_codes is not None else {4401, 4403}
    try:
        async with websockets.connect(ws_uri) as websocket:
            await asyncio.sleep(0.5)
            await websocket.recv()
    except websockets.exceptions.ConnectionClosedError as exc:
        if exc.code not in allowed_codes:
            raise AssertionError(
                f"unexpected tunnel close code {exc.code!r}, expected one of {sorted(allowed_codes)}"
            ) from exc
        return exc.code
    except websockets.exceptions.InvalidStatusCode as exc:
        if 403 not in allowed_codes and 401 not in allowed_codes:
            raise AssertionError(
                f"tunnel rejected with HTTP {exc.status_code}, expected WS close codes {sorted(allowed_codes)}"
            ) from exc
        return exc.status_code
    raise AssertionError("tunnel connection was not rejected")


async def wait_tunnel_json(
    websocket: Any,
    *,
    expected_type: str,
    timeout: float = 10.0,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        raw = await asyncio.wait_for(websocket.recv(), timeout=min(remaining, 2.0))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            continue
        message_type = payload.get("type")
        if message_type == expected_type:
            return payload
    raise AssertionError(f"timeout waiting tunnel frame type={expected_type!r}")


async def wait_tunnel_error_frame(
    websocket: Any,
    *,
    error_code: str,
    timeout: float = 10.0,
) -> dict[str, object]:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        remaining = deadline - asyncio.get_event_loop().time()
        raw = await asyncio.wait_for(websocket.recv(), timeout=min(remaining, 2.0))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            continue
        if payload.get("type") == "error" and payload.get("error_code") == error_code:
            return payload
    raise AssertionError(f"timeout waiting tunnel error frame error_code={error_code!r}")


async def run_fake_device_mcp_responder(websocket: Any) -> None:
    while True:
        raw = await websocket.recv()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            continue
        message_type = payload.get("type")
        if message_type == "policy":
            continue
        if message_type != "mcp_request":
            continue
        request_id = payload.get("request_id")
        method = payload.get("method")
        if not isinstance(request_id, str) or not isinstance(method, str):
            continue
        response = {
            "type": "mcp_response",
            "request_id": request_id,
            "result": {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": [{"name": "local_tool", "method": method}]},
            },
        }
        await websocket.send(json.dumps(response))
