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

from apps.flows.src.container import get_container
from apps.flows.src.models.operator_schemas import (
    OperatorTaskClaimCommand,
    OperatorTaskCompleteCommand,
    OperatorTaskMessageCommand,
)
from apps.flows.src.services.operator_handoff_service import operator_task_to_out
from core.context import get_context, set_context
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import User
from core.types import JsonObject, parse_json_object
from core.websocket import (
    CommandHandler,
    WsCommandError,
    register_ws_command_handler,
    validate_ws_payload,
)

logger = get_logger(__name__)


CMD_OPERATOR_CLAIM = "flows/operator_task/claim_requested"
CMD_OPERATOR_POST_MESSAGE = "flows/operator_task/post_message_requested"
CMD_OPERATOR_COMPLETE = "flows/operator_task/complete_requested"


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
    _ = set_context(ctx)
    return ctx


def _company_id() -> str:
    ctx = get_context()
    if ctx and ctx.active_company:
        return ctx.active_company.company_id
    raise WsCommandError("ws_no_company", "Нет active_company в контексте")


async def _handle_operator_claim(payload: JsonObject, user: User) -> JsonObject:
    command = validate_ws_payload(OperatorTaskClaimCommand, payload)
    _ = await _ensure_ws_context(user)
    container = get_container()
    company_id = _company_id()
    try:
        await container.operator_handoff_service.claim_task(
            company_id=company_id, task_id=command.task_id, operator_user_id=user.user_id
        )
    except PermissionError as exc:
        raise WsCommandError("forbidden", str(exc)) from exc
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc)) from exc
    updated = await container.operator_repository.get_task(company_id, command.task_id)
    if updated is None:
        raise WsCommandError("not_found", f"Задача {command.task_id} не найдена")
    flow_config = await container.flow_repository.get(updated.flow_id)
    return parse_json_object(
        operator_task_to_out(updated, flow_config=flow_config).model_dump_json(),
        "OperatorTaskOut",
    )


async def _handle_operator_post_message(payload: JsonObject, user: User) -> JsonObject:
    command = validate_ws_payload(OperatorTaskMessageCommand, payload)
    _ = await _ensure_ws_context(user)
    container = get_container()
    company_id = _company_id()
    try:
        await container.operator_handoff_service.publish_operator_message_to_user_stream(
            company_id=company_id,
            task_id=command.task_id,
            operator_user_id=user.user_id,
            text=command.text,
            file_ids=command.file_ids,
        )
    except PermissionError as exc:
        raise WsCommandError("forbidden", str(exc)) from exc
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc)) from exc
    return {"status": "sent", "task_id": command.task_id}


async def _handle_operator_complete(payload: JsonObject, user: User) -> JsonObject:
    command = validate_ws_payload(OperatorTaskCompleteCommand, payload)
    _ = await _ensure_ws_context(user)
    container = get_container()
    company_id = _company_id()
    try:
        await container.operator_handoff_service.complete_handoff(
            company_id=company_id,
            task_id=command.task_id,
            operator_user_id=user.user_id,
            resolution=command.resolution,
            file_ids=command.file_ids,
        )
    except PermissionError as exc:
        raise WsCommandError("forbidden", str(exc)) from exc
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc)) from exc
    return {"status": "completed", "task_id": command.task_id}


_HANDLERS: dict[str, CommandHandler] = {
    CMD_OPERATOR_CLAIM: _handle_operator_claim,
    CMD_OPERATOR_POST_MESSAGE: _handle_operator_post_message,
    CMD_OPERATOR_COMPLETE: _handle_operator_complete,
}


def register_flows_ws_commands() -> None:
    """Зарегистрировать все flows command-handler'ы. Вызывать на on_startup."""
    for command_type, handler in _HANDLERS.items():
        register_ws_command_handler(command_type, handler)
    logger.info("Flows WS command-handlers зарегистрированы (%d команд)", len(_HANDLERS))
