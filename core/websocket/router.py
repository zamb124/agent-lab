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

Каждый WS connect и каждая команда выполняются в request-лог-скоупе:
сначала на коннект ставится connection-уровневый ``request_id`` (формат
``ws-conn:<uuid>``), затем для каждой команды — командный ``request_id``
из фрейма (если присутствует) или сгенерированный ``ws-cmd:<uuid>``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import get_settings
from core.context import clear_context, set_context
from core.logging import (
    bind_log_context,
    enter_request_scope,
    exit_request_scope,
    get_logger,
)
from core.logging.attributes import (
    EVENT_WS_COMMAND,
    EVENT_WS_CONNECTED,
    EVENT_WS_DISCONNECTED,
    LOG_USER_ID,
    LOG_WS_COMMAND,
    LOG_WS_REQUEST_ID,
)
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import User
from core.websocket.auth import get_user_from_websocket
from core.websocket.command_router import (
    WsCommandError,
    derive_failed_type,
    dispatch_ws_command,
)
from core.websocket.manager import notification_manager

logger = get_logger(__name__)


async def _build_ws_context(websocket: WebSocket, user: User) -> Context:
    container = websocket.app.state.container
    company = None
    user_companies = []
    active_company_id = user.active_company_id
    if isinstance(active_company_id, str) and active_company_id:
        company = await container.company_repository.get(active_company_id)
        if company is not None:
            user_companies = [company]
    return Context(
        user=user,
        active_company=company,
        user_companies=user_companies,
        channel="ws",
        language=Language.RU,
        container=container,
    )

router = APIRouter()


def _build_failure_frame(request_id: str | None, command_type: str | None, code: str, detail: str) -> dict[str, Any]:
    fail_type = derive_failed_type(command_type) if command_type else "system/ws/invalid_frame"
    return {
        "request_id": request_id,
        "type": fail_type,
        "payload": {"error_code": code, "error_detail": detail},
    }


async def _handle_command_frame(
    websocket: WebSocket,
    frame: dict[str, Any],
    user: User,
    *,
    service_name: str,
    connection_request_id: str,
) -> None:
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

    command_request_id = f"ws-cmd:{uuid.uuid4().hex}"
    trace_id = f"ws:{uuid.uuid4().hex}"

    company_id = (
        user.active_company_id
        if isinstance(user.active_company_id, str) and user.active_company_id
        else None
    )

    scope_token = enter_request_scope(
        request_id=command_request_id,
        trace_id=trace_id,
        service_name=service_name,
        user_id=user.user_id,
        company_id=company_id,
        **{
            LOG_WS_REQUEST_ID: request_id,
            LOG_WS_COMMAND: command_type,
            "ws.connection_request_id": connection_request_id,
        },
    )
    context = await _build_ws_context(websocket, user)
    set_context(context)
    try:
        logger.info(EVENT_WS_COMMAND, **{LOG_WS_COMMAND: command_type})
        try:
            reply_type, reply_payload = await dispatch_ws_command(command_type, payload, user)
        except WsCommandError as err:
            reply_type = derive_failed_type(command_type)
            reply_payload = {"error_code": err.code, "error_detail": err.detail}
        except Exception as exc:
            logger.exception(
                "ws.command_crashed",
                **{
                    LOG_WS_COMMAND: command_type,
                    "exception.type": type(exc).__name__,
                },
            )
            reply_type = derive_failed_type(command_type)
            reply_payload = {"error_code": "ws_internal_error", "error_detail": str(exc)}
    finally:
        clear_context()
        exit_request_scope(scope_token)
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
        logger.warning("ws.auth_required")
        return

    user_id = user.user_id
    company_id = user.active_company_id
    settings = get_settings()
    service_name = settings.server.name
    connection_request_id = f"ws-conn:{uuid.uuid4().hex}"
    connection_trace_id = f"ws:{uuid.uuid4().hex}"

    scope_token = enter_request_scope(
        request_id=connection_request_id,
        trace_id=connection_trace_id,
        service_name=service_name,
        user_id=user_id,
        company_id=company_id if isinstance(company_id, str) and company_id else None,
        **{
            "ws.connection_kind": "notifications",
        },
    )
    logger.info(EVENT_WS_CONNECTED, **{LOG_USER_ID: user_id})

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
                logger.warning(
                    "ws.invalid_json",
                    **{LOG_USER_ID: user_id, "exception.message": str(exc)},
                )
                continue
            if not isinstance(frame, dict):
                logger.warning("ws.frame_not_object", **{LOG_USER_ID: user_id})
                continue
            await _handle_command_frame(
                websocket,
                frame,
                user,
                service_name=service_name,
                connection_request_id=connection_request_id,
            )
            # После выхода из scope команды восстановим бинд connection-полей,
            # чтобы записи `notification_manager.disconnect` несли user_id.
            bind_log_context(
                **{LOG_USER_ID: user_id},
            )
    except WebSocketDisconnect:
        logger.debug("ws.disconnect_normal", **{LOG_USER_ID: user_id})
    except Exception as exc:
        logger.exception(
            "ws.error",
            **{LOG_USER_ID: user_id, "exception.type": type(exc).__name__},
        )
    finally:
        await notification_manager.disconnect(websocket, user_id)
        logger.info(EVENT_WS_DISCONNECTED, **{LOG_USER_ID: user_id})
        exit_request_scope(scope_token)


@router.get("/ws/stats")
async def websocket_stats() -> dict:
    return notification_manager.get_stats()
