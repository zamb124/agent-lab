"""HTTP-вход bus → `op_*` владельца. Монтируется на каждый HTTP-сервис."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from core.config import get_settings
from core.context import get_context
from core.context.command import reset_command_event_id, set_command_event_id
from core.di.state import app_di
from core.events import publish_event_to_user
from core.events.contract import PlatformEvent
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_WS_COMMAND,
    EVENT_WS_COMMAND_FINISHED,
    LOG_WS_COMMAND,
    LOG_WS_COMMAND_DURATION_MS,
    LOG_WS_COMMAND_STATUS,
)
from core.observability.error_payload import try_merge_platform_error_into_dict
from core.realtime.models import RealtimeCommandAccepted
from core.types import JsonObject, JsonValue
from core.websocket.command_router import dispatch_ws_command

logger = get_logger(__name__)

router = APIRouter()


def merge_command_failure_payload(
    payload: JsonObject,
    *,
    trace_id: str | None,
    platform_request_id: str | None,
    service_name: str,
    active_company_id: str | None,
) -> JsonObject:
    settings = get_settings()
    return try_merge_platform_error_into_dict(
        payload,
        trace_id=trace_id,
        platform_request_id=platform_request_id,
        service_name=service_name,
        logging_cfg=settings.logging,
        active_company_id=active_company_id,
    )


@router.post("/internal/realtime/command", response_model=RealtimeCommandAccepted)
async def execute_realtime_command(
    event: PlatformEvent,
    request: Request,
) -> RealtimeCommandAccepted:
    di = app_di(request)
    context = get_context()
    if context is None:
        raise RuntimeError("execute_realtime_command requires request context")
    command_start = time.perf_counter()
    logger.info(EVENT_WS_COMMAND, **{LOG_WS_COMMAND: event.type})
    command_token = set_command_event_id(event.event_id)
    try:
        reply_type, reply_payload = await dispatch_ws_command(
            event.type,
            event.payload,
            context.user,
            di,
        )
    finally:
        reset_command_event_id(command_token)
    command_status = "error" if reply_type.endswith("_failed") else "ok"
    command_duration_ms = round((time.perf_counter() - command_start) * 1000.0, 3)
    logger.info(
        EVENT_WS_COMMAND_FINISHED,
        **{
            LOG_WS_COMMAND: event.type,
            LOG_WS_COMMAND_DURATION_MS: command_duration_ms,
            LOG_WS_COMMAND_STATUS: command_status,
        },
    )
    published_payload: JsonValue = reply_payload
    if reply_payload is not None and reply_type.endswith("_failed"):
        company_id = context.active_company.company_id if context.active_company is not None else None
        published_payload = merge_command_failure_payload(
            reply_payload,
            trace_id=event.meta.trace_id,
            platform_request_id=event.meta.request_id,
            service_name=get_settings().server.name,
            active_company_id=company_id,
        )
    await publish_event_to_user(
        context.user.user_id,
        reply_type,
        published_payload,
        company_id=event.company_id,
        actor_user_id=context.user.user_id,
        causation_id=event.event_id,
        correlation_id=event.meta.correlation_id,
        trace_id=event.meta.trace_id,
        request_id=event.meta.request_id,
    )
    logger.info(
        "realtime.command.executed",
        event_id=event.event_id,
        event_type=event.type,
        reply_type=reply_type,
    )
    return RealtimeCommandAccepted(accepted=True, event_id=event.event_id)
