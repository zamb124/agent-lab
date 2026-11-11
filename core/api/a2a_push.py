"""``POST /{service}/api/v1/internal/a2a/push`` — приём A2A push webhook'ов.

Anonymous-маршрут (RouteRule в `route_config.py`): авторизация — bearer-токен
строки `PlatformA2APendingCall` (sha256-хеш в базе, провод — `Bearer <token>`).
Тело — ``StreamResponse`` ProtoJSON (``task`` | ``statusUpdate``); терминал —
consume + enqueue continuation; не-терминал — ACK без consume; повтор —
идемпотентный ACK.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from core.a2a.pending_call import PendingCallStatus, PlatformA2APendingCall
from core.a2a.push_callback import hash_callback_token
from core.a2a.task_states import wire_task_state_to_platform
from core.a2a.task_states import A2A_OPEN_TASK_STATES
from core.logging import get_logger
from core.tasks import enqueue
from core.types import JsonObject, parse_json_object, require_json_object

logger = get_logger(__name__)

a2a_push_router = APIRouter(tags=["a2a-push"])


def _bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _task_id_and_state(body: JsonObject) -> tuple[str | None, str | None]:
    """(taskId, platform state) из StreamResponse ProtoJSON кадра."""
    update = body.get("statusUpdate")
    if isinstance(update, dict):
        update_obj = require_json_object(update, "StreamResponse.statusUpdate")
        task_id = update_obj.get("taskId")
        status = update_obj.get("status")
        state_value = (
            require_json_object(status, "statusUpdate.status").get("state")
            if isinstance(status, dict)
            else None
        )
    else:
        task = body.get("task")
        if not isinstance(task, dict):
            return None, None
        task_obj = require_json_object(task, "StreamResponse.task")
        task_id = task_obj.get("id")
        status = task_obj.get("status")
        state_value = (
            require_json_object(status, "task.status").get("state")
            if isinstance(status, dict)
            else None
        )
    if not isinstance(task_id, str) or not task_id.strip():
        return None, None
    if not isinstance(state_value, str) or not state_value:
        return task_id, None
    return task_id, wire_task_state_to_platform(state_value)


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


@a2a_push_router.post("/internal/a2a/push")
async def a2a_push(request: Request) -> Response:
    token = _bearer_token(request)
    if token is None:
        return _error(401, "bearer token required")

    body = parse_json_object(await request.body(), "a2a.push")
    task_id, platform_state = _task_id_and_state(body)
    if task_id is None:
        return _error(400, "StreamResponse statusUpdate.taskId or task.id required")

    # Не-терминальные кадры (submitted/working) — liveness, consume не нужен.
    if platform_state is not None and platform_state in A2A_OPEN_TASK_STATES:
        return Response(status_code=200)
    if platform_state is None:
        return _error(400, "status.state required")

    row = await PlatformA2APendingCall.pending_by_id(task_id)
    if row is None:
        return _error(404, "unknown a2a task")
    if not hmac.compare_digest(hash_callback_token(token), row.callback_token_hash):
        return _error(403, "invalid callback token")

    consumed = await PlatformA2APendingCall.consume(task_id)
    if consumed is None:
        # Дубль webhook'а / sweeper уже добил — continuation поставлен, чистый ACK.
        return Response(status_code=200)

    try:
        _ = await enqueue(
            consumed.continuation_task,
            a2a_task_id=consumed.a2a_task_id,
            a2a_state=platform_state,
            a2a_payload=body,
            a2a_base_url=consumed.base_url,
            **consumed.continuation_kwargs,
        )
    except Exception:
        _ = await PlatformA2APendingCall.restore_pending(task_id)
        raise

    logger.info(
        "a2a.push.consumed",
        a2a_task_id=task_id,
        service=consumed.service,
        a2a_state=platform_state,
        continuation=consumed.continuation_task,
    )
    return Response(status_code=200)


__all__ = ["a2a_push_router", "PendingCallStatus"]
