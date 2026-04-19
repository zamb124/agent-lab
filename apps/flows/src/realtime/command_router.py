"""Регистрация WS command-handler'ов сервиса flows в `core.websocket`.

Каждая команда имеет каноничное имя `flows/<entity>/<verb>_requested` и
REST-зеркало с тем же payload в `apps/flows/src/api/v1/**` (или в
`apps/flows/src/api/a2a.py` для команд чата). Бизнес-логика — общая для
обоих транспортов.

Команды чата (`flows/chat/send_requested`, `flows/chat/cancel_requested`)
запускают/отменяют long-running стрим и сразу возвращают ack
`{ task_id, context_id }`. Сами события чата публикуются как
push-события `flows/chat/*` через `core.ui_events.publish_ui_event_to_user`
(см. `apps/flows/src/services/chat_stream_publisher.py`).

Команды operator (`flows/operator_task/claim_requested` и далее) — обычные
RPC: вызывают сервис, возвращают результат как payload `*_succeeded`.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Awaitable, Callable

from a2a.types import MessageSendParams, TaskIdParams

from apps.flows.src.channels import PermissionDenied
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.container import get_container
from apps.flows.src.services.chat_stream_publisher import (
    CHAT_EVENT_FAILED,
    stream_to_user,
)
from core.context import Context, get_context, set_context
from core.logging import get_logger
from core.models.identity_models import User
from core.ui_events import publish_ui_event_to_user
from core.websocket import WsCommandError, register_ws_command_handler

logger = get_logger(__name__)


# Имена WS-команд (канонические, single source of truth).
CMD_CHAT_SEND = "flows/chat/send_requested"
CMD_CHAT_CANCEL = "flows/chat/cancel_requested"
CMD_OPERATOR_CLAIM = "flows/operator_task/claim_requested"
CMD_OPERATOR_POST_MESSAGE = "flows/operator_task/post_message_requested"
CMD_OPERATOR_COMPLETE = "flows/operator_task/complete_requested"


# Активные стрим-таски на пользователя+task_id, чтобы cancel мог их прибить.
_active_chat_tasks: dict[str, asyncio.Task[None]] = {}


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise WsCommandError(
            "ws_invalid_payload",
            f"Поле '{key}' обязательно и должно быть непустой строкой",
        )
    return value


def _require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise WsCommandError(
            "ws_invalid_payload",
            f"Поле '{key}' обязательно и должно быть объектом",
        )
    return value


async def _resolve_chat_context_for_task(user: User) -> Context:
    """Снимок текущего контекста для фоновой таски стриминга.

    WS-handler выполняется внутри auth middleware (контекст инициализирован).
    Фоновая таска уже не имеет request-scope — переносим контекст явно.
    """
    ctx = get_context()
    if ctx is None:
        raise WsCommandError(
            "ws_no_context", "Нет контекста для команды flows/chat (auth-middleware не отработал)"
        )
    return ctx


async def _handle_chat_send(payload: dict[str, Any], user: User) -> dict[str, Any]:
    flow_id = _require_str(payload, "flow_id")
    params_dict = _require_dict(payload, "params")

    container = get_container()
    config = await container.flow_repository.get(flow_id)
    if not config:
        raise WsCommandError("flow_not_found", f"Flow '{flow_id}' не найден")

    context = await _resolve_chat_context_for_task(user)

    metadata = params_dict.get("metadata")
    if metadata is None:
        metadata = {}
        params_dict["metadata"] = metadata
    if not isinstance(metadata, dict):
        raise WsCommandError("ws_invalid_payload", "params.metadata должен быть объектом")
    metadata.setdefault("__user_groups__", list(getattr(user, "groups", []) or []))

    params = MessageSendParams(**params_dict)
    if params.message is None or not getattr(params.message, "messageId", None):
        raise WsCommandError("ws_invalid_payload", "params.message.messageId обязателен")

    ack_task_id = uuid.uuid4().hex
    correlation_id = f"{flow_id}:{user.user_id}:{int(time.time() * 1000)}"

    channel = A2AChannel(flow_id, context=context, flow_config=config)
    channel_context = {"user_groups": metadata["__user_groups__"]}

    async def _runner() -> None:
        token = set_context(context)
        try:
            await stream_to_user(
                user_id=user.user_id,
                channel=channel,
                params=params,
                channel_context=channel_context,
                correlation_id=correlation_id,
            )
        except PermissionDenied as err:
            await publish_ui_event_to_user(
                user_id=user.user_id,
                type=CHAT_EVENT_FAILED,
                payload={
                    "task_id": ack_task_id,
                    "state": "failed",
                    "final": True,
                    "error": str(err),
                    "message": None,
                },
                correlation_id=correlation_id,
            )
        finally:
            try:
                token.reset()
            except Exception:  # noqa: BLE001 — token может быть из другого loop'а в edge-cases
                pass
            _active_chat_tasks.pop(_chat_task_key(user.user_id, ack_task_id), None)

    task = asyncio.create_task(_runner(), name=f"flows-chat-stream:{ack_task_id}")
    _active_chat_tasks[_chat_task_key(user.user_id, ack_task_id)] = task

    context_id = getattr(params.message, "contextId", None)
    return {
        "task_id": ack_task_id,
        "context_id": context_id,
        "flow_id": flow_id,
        "correlation_id": correlation_id,
    }


def _chat_task_key(user_id: str, task_id: str) -> str:
    return f"{user_id}:{task_id}"


async def _handle_chat_cancel(payload: dict[str, Any], user: User) -> dict[str, Any]:
    flow_id = _require_str(payload, "flow_id")
    task_id = _require_str(payload, "task_id")

    container = get_container()
    config = await container.flow_repository.get(flow_id)
    if not config:
        raise WsCommandError("flow_not_found", f"Flow '{flow_id}' не найден")

    context = await _resolve_chat_context_for_task(user)

    handle_task = _active_chat_tasks.pop(_chat_task_key(user.user_id, task_id), None)
    if handle_task is not None and not handle_task.done():
        handle_task.cancel()

    channel = A2AChannel(flow_id, context=context, flow_config=config)
    cancelled = await channel.on_cancel_task(TaskIdParams(id=task_id))
    return {
        "task_id": task_id,
        "cancelled": cancelled is not None,
    }


def _company_id(user: User) -> str:
    ctx = get_context()
    if ctx and ctx.active_company:
        return ctx.active_company.company_id
    raise WsCommandError("ws_no_company", "Нет active_company в контексте")


async def _handle_operator_claim(payload: dict[str, Any], user: User) -> dict[str, Any]:
    task_id = _require_str(payload, "task_id")
    container = get_container()
    company_id = _company_id(user)
    try:
        await container.operator_handoff_service.claim_task(
            company_id=company_id, task_id=task_id, operator_user_id=user.user_id
        )
    except PermissionError as exc:
        raise WsCommandError("forbidden", str(exc))
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc))
    updated = await container.operator_repository.get_task(company_id, task_id)
    if updated is None:
        raise WsCommandError("not_found", f"Задача {task_id} не найдена")
    return _operator_task_dump(updated)


async def _handle_operator_post_message(payload: dict[str, Any], user: User) -> dict[str, Any]:
    task_id = _require_str(payload, "task_id")
    text = payload.get("text")
    if not isinstance(text, str):
        raise WsCommandError("ws_invalid_payload", "Поле 'text' обязательно")
    file_ids = payload.get("file_ids") or []
    if not isinstance(file_ids, list):
        raise WsCommandError("ws_invalid_payload", "Поле 'file_ids' должно быть массивом")

    container = get_container()
    company_id = _company_id(user)
    try:
        await container.operator_handoff_service.publish_operator_message_to_user_stream(
            company_id=company_id,
            task_id=task_id,
            operator_user_id=user.user_id,
            text=text,
            file_ids=[str(fid) for fid in file_ids],
        )
    except PermissionError as exc:
        raise WsCommandError("forbidden", str(exc))
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc))
    return {"status": "sent", "task_id": task_id}


async def _handle_operator_complete(payload: dict[str, Any], user: User) -> dict[str, Any]:
    task_id = _require_str(payload, "task_id")
    resolution = payload.get("resolution")
    if not isinstance(resolution, str):
        raise WsCommandError("ws_invalid_payload", "Поле 'resolution' обязательно")
    file_ids = payload.get("file_ids") or []
    if not isinstance(file_ids, list):
        raise WsCommandError("ws_invalid_payload", "Поле 'file_ids' должно быть массивом")

    container = get_container()
    company_id = _company_id(user)
    try:
        await container.operator_handoff_service.complete_handoff(
            company_id=company_id,
            task_id=task_id,
            operator_user_id=user.user_id,
            resolution=resolution,
            file_ids=[str(fid) for fid in file_ids],
        )
    except PermissionError as exc:
        raise WsCommandError("forbidden", str(exc))
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc))
    return {"status": "completed", "task_id": task_id}


def _operator_task_dump(task: Any) -> dict[str, Any]:
    if hasattr(task, "model_dump"):
        return task.model_dump(mode="json")
    if isinstance(task, dict):
        return task
    fields: dict[str, Any] = {}
    for key in (
        "id",
        "company_id",
        "queue_id",
        "flow_id",
        "session_id",
        "context_id",
        "status",
        "claimed_by_user_id",
        "end_user_id",
        "skill_id",
        "created_at",
        "updated_at",
    ):
        value = getattr(task, key, None)
        if value is not None:
            fields[key] = value if isinstance(value, (str, int, float, bool, list, dict)) else str(value)
    return fields


_HANDLERS: dict[str, Callable[[dict[str, Any], User], Awaitable[dict[str, Any] | None]]] = {
    CMD_CHAT_SEND: _handle_chat_send,
    CMD_CHAT_CANCEL: _handle_chat_cancel,
    CMD_OPERATOR_CLAIM: _handle_operator_claim,
    CMD_OPERATOR_POST_MESSAGE: _handle_operator_post_message,
    CMD_OPERATOR_COMPLETE: _handle_operator_complete,
}


def register_flows_ws_commands() -> None:
    """Зарегистрировать все flows command-handler'ы. Вызывать на on_startup."""
    for command_type, handler in _HANDLERS.items():
        register_ws_command_handler(command_type, handler)
    logger.info("Flows WS command-handlers зарегистрированы (%d команд)", len(_HANDLERS))
