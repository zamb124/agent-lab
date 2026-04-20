"""Регистрация WS command-handler'ов сервиса flows в `core.websocket`.

Каждая команда имеет каноничное имя `flows/<entity>/<verb>_requested` и
REST-зеркало с тем же payload в `apps/flows/src/api/v1/**`. Бизнес-логика —
общая для обоих транспортов.

Команды operator (`flows/operator_task/claim_requested` и далее) — обычные
RPC: вызывают сервис, возвращают результат как payload `*_succeeded`.

Чат сервиса flows работает по стандартному A2A SSE
(`POST /flows/api/v1/{flow_id}` с JSON-RPC `message/stream` /
`tasks/cancel`) и WS-команд не использует — см. `apps/flows/src/api/a2a.py`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from apps.flows.src.container import get_container
from core.context import get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import WsCommandError, register_ws_command_handler

logger = get_logger(__name__)


CMD_OPERATOR_CLAIM = "flows/operator_task/claim_requested"
CMD_OPERATOR_POST_MESSAGE = "flows/operator_task/post_message_requested"
CMD_OPERATOR_COMPLETE = "flows/operator_task/complete_requested"


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise WsCommandError(
            "ws_invalid_payload",
            f"Поле '{key}' обязательно и должно быть непустой строкой",
        )
    return value


async def _ensure_ws_context(user: User) -> Context:
    """Гарантирует Context с `active_company` для WS-команды.

    HTTP `AuthMiddleware` на WebSocket-эндпоинты не распространяется
    (`BaseHTTPMiddleware` обслуживает только HTTP), поэтому контекст для
    WS-команд собирается здесь: грузим Company из `company_repository`
    по `user.active_company_id` и кладём контекст в contextvars текущей
    корутины.
    """
    existing = get_context()
    if existing is not None and existing.active_company is not None:
        return existing

    company_id = user.active_company_id
    if not company_id:
        raise WsCommandError(
            "ws_no_company",
            "У пользователя нет active_company_id для WS-команды flows.",
        )

    container = get_container()
    company = await container.company_repository.get(company_id)
    if company is None:
        raise WsCommandError(
            "ws_no_company",
            f"Компания {company_id!r} не найдена в репозитории.",
        )

    ctx = Context(
        user=user,
        host="",
        channel="ws",
        active_company=company,
        user_companies=[company],
        active_namespace="default",
    )
    set_context(ctx)
    return ctx


def _company_id(user: User) -> str:
    ctx = get_context()
    if ctx and ctx.active_company:
        return ctx.active_company.company_id
    raise WsCommandError("ws_no_company", "Нет active_company в контексте")


async def _handle_operator_claim(payload: dict[str, Any], user: User) -> dict[str, Any]:
    task_id = _require_str(payload, "task_id")
    await _ensure_ws_context(user)
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

    await _ensure_ws_context(user)
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

    await _ensure_ws_context(user)
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
    CMD_OPERATOR_CLAIM: _handle_operator_claim,
    CMD_OPERATOR_POST_MESSAGE: _handle_operator_post_message,
    CMD_OPERATOR_COMPLETE: _handle_operator_complete,
}


def register_flows_ws_commands() -> None:
    """Зарегистрировать все flows command-handler'ы. Вызывать на on_startup."""
    for command_type, handler in _HANDLERS.items():
        register_ws_command_handler(command_type, handler)
    logger.info("Flows WS command-handlers зарегистрированы (%d команд)", len(_HANDLERS))
