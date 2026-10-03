"""
WebSocket tunnel HumanitecAgent: исходящее соединение с ПК пользователя.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from apps.agent.service import (
    get_device_record,
    is_device_token_denied,
    mark_device_tunnel_offline,
    mark_device_tunnel_online,
)
from apps.agent.tunnel_bus import (
    register_tunnel_connection,
    unregister_tunnel_connection,
)
from apps.agent.tunnel_registry import handle_device_mcp_message
from apps.frontend.di import Di
from core.logging import get_logger
from core.types import JsonObject, parse_json_object
from core.utils.tokens import TokenService
from core.websocket import WsCommandError

logger = get_logger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent-tunnel"])


def _device_id_from_token(token: str) -> tuple[str, str | None]:
    token_service = TokenService()
    token_data = token_service.validate_token(token)
    if token_data is None:
        raise WsCommandError("unauthorized", "Invalid device token", error_code="unauthorized")
    metadata = token_data.metadata
    token_purpose = metadata.get("token_purpose")
    if token_purpose != "device":
        raise WsCommandError("unauthorized", "Token is not a device token", error_code="unauthorized")
    device_id = metadata.get("device_id")
    if not isinstance(device_id, str) or not device_id:
        raise WsCommandError("unauthorized", "device_id is missing from the token", error_code="unauthorized")
    if device_id == "pending":
        raise WsCommandError(
            "unauthorized",
            "device token is not bound to a device yet",
            error_code="unauthorized",
        )
    device_jti = metadata.get("jti")
    resolved_jti = device_jti if isinstance(device_jti, str) and device_jti else None
    return device_id, resolved_jti


@router.websocket("/tunnel")
async def agent_tunnel_websocket(
    websocket: WebSocket,
    di: Di,
    token: Annotated[str, Query(description="Device JWT")],
) -> None:
    await websocket.accept()

    try:
        device_id, device_jti = _device_id_from_token(token)
        device = await get_device_record(di, device_id)
    except WsCommandError as exc:
        await websocket.close(code=4401, reason=exc.detail)
        return

    if not device.is_active:
        await websocket.close(code=4403, reason="Устройство деактивировано")
        return

    if await is_device_token_denied(di, device_id, device_jti=device_jti):
        await websocket.close(code=4401, reason="Device token revoked")
        return

    if (
        not device.policy.shell_enabled
        and not device.policy.browser_enabled
        and not device.policy.allowed_roots
    ):
        await websocket.close(code=4403, reason="Device policy blocks tunnel")
        return

    register_tunnel_connection(device_id, websocket)
    policy_frame = {
        "type": "policy",
        "policy": device.policy.model_dump(),
    }
    await websocket.send_text(json.dumps(policy_frame))
    await mark_device_tunnel_online(di, device_id=device_id)
    logger.info("agent.tunnel.connected", device_id=device_id, company_id=device.company_id)

    try:
        while True:
            raw_message = await websocket.receive_text()
            device = await get_device_record(di, device_id)
            if not device.is_active:
                await websocket.close(code=4403, reason="Устройство деактивировано")
                break
            if await is_device_token_denied(di, device_id, device_jti=device_jti):
                await websocket.close(code=4401, reason="Device token revoked")
                break

            message_payload = parse_json_object(raw_message, "agent.tunnel.message")
            message_type = message_payload.get("type")
            if message_type == "ping":
                await mark_device_tunnel_online(di, device_id=device_id)
                pong: JsonObject = {"type": "pong", "device_id": device_id}
                await websocket.send_text(json.dumps(pong))
                continue

            mcp_reply = handle_device_mcp_message(device_id, message_payload)
            if mcp_reply is not None:
                await mark_device_tunnel_online(di, device_id=device_id)
                await websocket.send_text(json.dumps(mcp_reply))
                continue

            if message_type == "mcp_response":
                await mark_device_tunnel_online(di, device_id=device_id)
                continue

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "error_code": "unsupported_message_type",
                        "detail": "Поддерживаются type=ping, type=mcp, type=mcp_response",
                    }
                )
            )
    except WebSocketDisconnect:
        logger.info("agent.tunnel.disconnected", device_id=device_id)
    finally:
        unregister_tunnel_connection(device_id)
        await mark_device_tunnel_offline(di, device_id=device_id)
