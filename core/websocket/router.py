"""
WebSocket-роутер: единый endpoint `/ws/notifications`.

После аутентификации сокет регистрируется в `NotificationManager`. По одному
сокету идут два потока:

1. **Push** (server -> client): менеджер форвардит UIEvent-фреймы из
   Redis-канала `platform:ui_events`.
2. **RPC request-reply** (client -> server -> client): клиент шлёт
   `{ request_id, type, payload }`, сервер ищет handler в
   `core.websocket.command_router` и отвечает обратным фреймом
   `{ request_id, type: *_succeeded|*_failed, payload }`.

Команды без зарегистрированного handler'а возвращают `*_failed` с
`error_code = ws_handler_not_found`. Невалидный JSON или фрейм без `type` —
ack'аются `system/ws/invalid_frame`.

Heartbeat: текстовый `ping` -> `pong` (старый контракт сохранён).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.logging import get_logger
from core.websocket.auth import get_user_from_websocket
from core.websocket.command_router import (
    WsCommandError,
    derive_failed_type,
    dispatch_ws_command,
)
from core.websocket.manager import notification_manager

logger = get_logger(__name__)

router = APIRouter()


def _build_failure_frame(request_id: str | None, command_type: str | None, code: str, detail: str) -> dict[str, Any]:
    fail_type = derive_failed_type(command_type) if command_type else "system/ws/invalid_frame"
    return {
        "request_id": request_id,
        "type": fail_type,
        "payload": {"error_code": code, "error_detail": detail},
    }


async def _handle_command_frame(websocket: WebSocket, frame: dict[str, Any], user) -> None:
    request_id = frame.get("request_id")
    command_type = frame.get("type")
    payload = frame.get("payload")
    if not isinstance(request_id, str) or not request_id:
        await websocket.send_text(json.dumps(
            _build_failure_frame(None, None, "ws_invalid_frame", "request_id required (string)"),
            ensure_ascii=False,
        ))
        return
    if not isinstance(command_type, str) or not command_type:
        await websocket.send_text(json.dumps(
            _build_failure_frame(request_id, None, "ws_invalid_frame", "type required (string)"),
            ensure_ascii=False,
        ))
        return
    try:
        reply_type, reply_payload = await dispatch_ws_command(command_type, payload, user)
    except WsCommandError as err:
        reply_type = derive_failed_type(command_type)
        reply_payload = {"error_code": err.code, "error_detail": err.detail}
    except Exception as exc:
        logger.exception("WS command %s crashed for user=%s", command_type, user.user_id)
        reply_type = derive_failed_type(command_type)
        reply_payload = {"error_code": "ws_internal_error", "error_detail": str(exc)}
    await websocket.send_text(json.dumps(
        {"request_id": request_id, "type": reply_type, "payload": reply_payload},
        ensure_ascii=False,
    ))


@router.websocket("/ws/notifications")
async def notifications_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()

    user = await get_user_from_websocket(websocket)
    if not user or not user.user_id:
        await websocket.close(code=1008, reason="Authentication required")
        logger.warning("WS rejected: auth required")
        return

    user_id = user.user_id
    company_id = user.active_company_id

    await notification_manager.connect(websocket, user_id, company_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
                continue
            try:
                frame = json.loads(data)
            except json.JSONDecodeError as exc:
                logger.warning("WS invalid JSON from user=%s: %s", user_id, exc)
                continue
            if not isinstance(frame, dict):
                logger.warning("WS frame must be object from user=%s", user_id)
                continue
            await _handle_command_frame(websocket, frame, user)
    except WebSocketDisconnect:
        logger.debug("WS disconnect (normal): user=%s", user_id)
    except Exception as exc:
        logger.error("WS error: user=%s error=%s", user_id, exc, exc_info=True)
    finally:
        await notification_manager.disconnect(websocket, user_id)


@router.get("/ws/stats")
async def websocket_stats() -> dict:
    return notification_manager.get_stats()
