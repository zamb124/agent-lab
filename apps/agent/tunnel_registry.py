"""
Реестр активных tunnel WebSocket соединений HumanitecAgent.
"""

import asyncio
import json
import uuid

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from apps.agent.models import DevicePolicy
from core.logging import get_logger
from core.types import JsonObject, parse_json_object

logger = get_logger(__name__)

_tunnel_sockets: dict[str, WebSocket] = {}
_pending_mcp_responses: dict[str, asyncio.Future[JsonObject]] = {}


def register_tunnel_socket(device_id: str, websocket: WebSocket) -> None:
    _tunnel_sockets[device_id] = websocket


def unregister_tunnel_socket(device_id: str) -> None:
    _ = _tunnel_sockets.pop(device_id, None)


def is_tunnel_socket_registered(device_id: str) -> bool:
    return device_id in _tunnel_sockets


def register_pending_mcp_response(request_id: str, response_future: asyncio.Future[JsonObject]) -> None:
    _pending_mcp_responses[request_id] = response_future


def unregister_pending_mcp_response(request_id: str) -> None:
    _ = _pending_mcp_responses.pop(request_id, None)


async def disconnect_tunnel_device(device_id: str) -> None:
    websocket = _tunnel_sockets.get(device_id)
    if websocket is None:
        return
    unregister_tunnel_socket(device_id)
    try:
        await asyncio.wait_for(
            websocket.close(code=4403, reason="Device revoked"),
            timeout=2.0,
        )
    except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError) as exc:
        logger.info("agent.tunnel.disconnect_close_failed", device_id=device_id, detail=str(exc))


async def send_mcp_request_local(
    device_id: str,
    *,
    method: str,
    params: JsonObject,
    request_id: str | None = None,
    timeout_seconds: float = 30.0,
) -> JsonObject:
    websocket = _tunnel_sockets.get(device_id)
    if websocket is None:
        raise ValueError(f"Device tunnel offline: {device_id}")

    resolved_request_id = request_id if request_id is not None else str(uuid.uuid4())
    response_future: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()
    _pending_mcp_responses[resolved_request_id] = response_future
    outbound = {
        "type": "mcp_request",
        "request_id": resolved_request_id,
        "method": method,
        "params": params,
    }
    try:
        await websocket.send_text(json.dumps(outbound))
        return await asyncio.wait_for(response_future, timeout=timeout_seconds)
    except WebSocketDisconnect as exc:
        raise ValueError(f"Device tunnel disconnected: {device_id}") from exc
    finally:
        _ = _pending_mcp_responses.pop(resolved_request_id, None)


def resolve_mcp_response(request_id: str, payload: JsonObject) -> bool:
    pending = _pending_mcp_responses.get(request_id)
    if pending is None or pending.done():
        return False
    pending.set_result(payload)
    return True


def reject_mcp_response(request_id: str, error_detail: str) -> bool:
    pending = _pending_mcp_responses.get(request_id)
    if pending is None or pending.done():
        return False
    pending.set_exception(ValueError(error_detail))
    return True


async def push_device_policy_to_tunnel(device_id: str, policy: DevicePolicy) -> None:
    websocket = _tunnel_sockets.get(device_id)
    if websocket is None:
        return
    outbound = {
        "type": "policy",
        "policy": policy.model_dump(),
    }
    await websocket.send_text(json.dumps(outbound))


def handle_device_mcp_message(
    device_id: str,
    message_payload: JsonObject,
) -> JsonObject | None:
    message_type = message_payload.get("type")
    if message_type == "mcp_response":
        request_id = message_payload.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            return {
                "type": "error",
                "error_code": "invalid_mcp_response",
                "detail": "request_id обязателен для mcp_response",
            }
        result_raw = message_payload.get("result")
        if result_raw is None:
            error_detail = message_payload.get("error_detail")
            if isinstance(error_detail, str) and error_detail:
                _ = reject_mcp_response(request_id, error_detail)
            else:
                _ = reject_mcp_response(request_id, "mcp_response без result")
            return None
        if not isinstance(result_raw, dict):
            return {
                "type": "error",
                "error_code": "invalid_mcp_response",
                "detail": "result должен быть JSON object",
            }
        result = parse_json_object(json.dumps(result_raw), "agent.tunnel.mcp_response.result")
        if resolve_mcp_response(request_id, result):
            return None
        _ = reject_mcp_response(request_id, f"Неизвестный request_id: {request_id}")
        return {
            "type": "error",
            "error_code": "unknown_mcp_request",
            "detail": f"Неизвестный request_id: {request_id}",
        }

    if message_type == "mcp":
        logger.info("agent.tunnel.mcp_from_device", device_id=device_id)
        return {
            "type": "mcp_ack",
            "device_id": device_id,
            "received": True,
        }

    return None
