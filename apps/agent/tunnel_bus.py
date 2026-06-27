"""
Redis-backed маршрутизация HumanitecAgent tunnel между frontend pod-ами.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import TYPE_CHECKING

from apps.agent.tunnel_registry import (
    disconnect_tunnel_device,
    is_tunnel_socket_registered,
    register_pending_mcp_response,
    register_tunnel_socket,
    reject_mcp_response,
    resolve_mcp_response,
    send_mcp_request_local,
    unregister_pending_mcp_response,
    unregister_tunnel_socket,
)
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.types import JsonObject, parse_json_object
from core.utils.background import run_with_log_context

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = get_logger(__name__)

TUNNEL_MCP_REQUEST_CHANNEL = "platform:agent_tunnel_mcp_request"
TUNNEL_MCP_RESPONSE_CHANNEL = "platform:agent_tunnel_mcp_response"
TUNNEL_DISCONNECT_CHANNEL = "platform:agent_tunnel_disconnect"

POD_INSTANCE_ID = os.environ.get("HOSTNAME", f"frontend-{uuid.uuid4().hex[:8]}")


def get_pod_instance_id() -> str:
    return os.environ.get("HOSTNAME", POD_INSTANCE_ID)

_listener_task: asyncio.Task[None] | None = None
_listener_lock = asyncio.Lock()


def _parse_bus_message(raw_message: str, label: str) -> JsonObject:
    return parse_json_object(raw_message, label)


async def start_tunnel_bus_listener(redis_client: RedisClient) -> None:
    global _listener_task
    async with _listener_lock:
        if _listener_task is not None and not _listener_task.done():
            return
        _listener_task = run_with_log_context(
            _tunnel_bus_loop(redis_client),
            name="agent_tunnel_bus",
            background_kind="startup",
        )


async def stop_tunnel_bus_listener() -> None:
    global _listener_task
    async with _listener_lock:
        if _listener_task is None:
            return
        _ = _listener_task.cancel()
        try:
            await _listener_task
        except asyncio.CancelledError:
            pass
        _listener_task = None


async def _tunnel_bus_loop(redis_client: RedisClient) -> None:
    pubsub = await redis_client.open_pubsub()
    await pubsub.subscribe(
        TUNNEL_MCP_REQUEST_CHANNEL,
        TUNNEL_MCP_RESPONSE_CHANNEL,
        TUNNEL_DISCONNECT_CHANNEL,
    )
    logger.info("agent.tunnel_bus.listener_started", pod_instance_id=get_pod_instance_id())
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                continue
            if message["type"] != "message":
                continue
            channel = message.get("channel")
            data = message.get("data")
            if channel == TUNNEL_MCP_REQUEST_CHANNEL:
                _ = run_with_log_context(
                    _handle_bus_mcp_request(redis_client, data),
                    name="agent_tunnel_bus_mcp_request",
                    background_kind="polling",
                )
                continue
            if channel == TUNNEL_MCP_RESPONSE_CHANNEL:
                _handle_bus_mcp_response(data)
                continue
            if channel == TUNNEL_DISCONNECT_CHANNEL:
                await _handle_bus_disconnect(data)
    except asyncio.CancelledError:
        raise
    finally:
        await pubsub.unsubscribe(
            TUNNEL_MCP_REQUEST_CHANNEL,
            TUNNEL_MCP_RESPONSE_CHANNEL,
            TUNNEL_DISCONNECT_CHANNEL,
        )
        await pubsub.aclose()
        logger.info("agent.tunnel_bus.listener_stopped", pod_instance_id=get_pod_instance_id())


async def _handle_bus_mcp_request(redis_client: RedisClient, raw_message: str) -> None:
    payload = _parse_bus_message(raw_message, "agent.tunnel_bus.mcp_request")
    device_id = payload.get("device_id")
    request_id = payload.get("request_id")
    mcp_method = payload.get("method")
    mcp_params_raw = payload.get("params")
    origin_pod = payload.get("origin_pod")
    timeout_seconds_raw = payload.get("timeout_seconds")
    if not isinstance(device_id, str) or not device_id:
        return
    if not isinstance(request_id, str) or not request_id:
        return
    if not isinstance(mcp_method, str) or not mcp_method:
        return
    if origin_pod == get_pod_instance_id():
        return
    if not is_tunnel_socket_registered(device_id):
        return
    if not isinstance(timeout_seconds_raw, (int, float)) or timeout_seconds_raw <= 0:
        timeout_seconds = 30.0
    else:
        timeout_seconds = float(timeout_seconds_raw)
    mcp_params = (
        _parse_bus_message(json.dumps(mcp_params_raw), "agent.tunnel_bus.mcp_params")
        if isinstance(mcp_params_raw, dict)
        else {}
    )
    try:
        result = await send_mcp_request_local(
            device_id,
            method=mcp_method,
            params=mcp_params,
            request_id=request_id,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        await _publish_mcp_response(
            redis_client,
            request_id=request_id,
            error_detail=str(exc),
        )
        return
    await _publish_mcp_response(redis_client, request_id=request_id, result=result)


def _handle_bus_mcp_response(raw_message: str) -> None:
    payload = _parse_bus_message(raw_message, "agent.tunnel_bus.mcp_response")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return
    error_detail = payload.get("error_detail")
    if isinstance(error_detail, str) and error_detail:
        _ = reject_mcp_response(request_id, error_detail)
        return
    result_raw = payload.get("result")
    if not isinstance(result_raw, dict):
        _ = reject_mcp_response(request_id, "mcp_response без result")
        return
    result = _parse_bus_message(json.dumps(result_raw), "agent.tunnel_bus.mcp_result")
    _ = resolve_mcp_response(request_id, result)


async def _handle_bus_disconnect(raw_message: str) -> None:
    payload = _parse_bus_message(raw_message, "agent.tunnel_bus.disconnect")
    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not device_id:
        return
    await disconnect_tunnel_device(device_id)


async def _publish_mcp_response(
    redis_client: RedisClient,
    *,
    request_id: str,
    result: JsonObject | None = None,
    error_detail: str | None = None,
) -> None:
    payload: JsonObject = {"request_id": request_id}
    if error_detail is not None:
        payload["error_detail"] = error_detail
    if result is not None:
        payload["result"] = result
    _ = await redis_client.publish(
        TUNNEL_MCP_RESPONSE_CHANNEL,
        json.dumps(payload),
    )


async def publish_tunnel_disconnect(redis_client: RedisClient, device_id: str) -> None:
    await disconnect_tunnel_device(device_id)
    _ = await redis_client.publish(
        TUNNEL_DISCONNECT_CHANNEL,
        json.dumps({"device_id": device_id}),
    )


async def send_mcp_request_to_device(
    redis_client: RedisClient,
    device_id: str,
    *,
    method: str,
    params: JsonObject,
    timeout_seconds: float = 30.0,
) -> JsonObject:
    if is_tunnel_socket_registered(device_id):
        return await send_mcp_request_local(
            device_id,
            method=method,
            params=params,
            timeout_seconds=timeout_seconds,
        )

    request_id = str(uuid.uuid4())
    response_future: asyncio.Future[JsonObject] = asyncio.get_running_loop().create_future()
    register_pending_mcp_response(request_id, response_future)
    outbound: JsonObject = {
        "device_id": device_id,
        "request_id": request_id,
        "method": method,
        "params": params,
        "origin_pod": get_pod_instance_id(),
        "timeout_seconds": timeout_seconds,
    }
    try:
        _ = await redis_client.publish(
            TUNNEL_MCP_REQUEST_CHANNEL,
            json.dumps(outbound),
        )
        return await asyncio.wait_for(response_future, timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        raise ValueError(f"Device tunnel offline: {device_id}") from exc
    finally:
        unregister_pending_mcp_response(request_id)


def register_tunnel_connection(device_id: str, websocket: WebSocket) -> None:
    register_tunnel_socket(device_id, websocket)


def unregister_tunnel_connection(device_id: str) -> None:
    unregister_tunnel_socket(device_id)
