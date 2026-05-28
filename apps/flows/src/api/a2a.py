"""
HTTP и JSON-RPC эндпоинты A2A для flows (a2a-sdk).
Полная реализация протокола; поддержаны все методы спецификации.
"""

import json
from collections.abc import AsyncGenerator, Mapping
from typing import cast

from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    MessageSendParams,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apps.flows.src.channels import PermissionDenied
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import BranchCreateRequest, BranchUpdateRequest, FlowConfig
from apps.flows.src.services.embed_target_resolver import EmbedTarget, resolve_embed_target
from core.context import get_context
from core.identity.embed_guest_turns import (
    EMBED_GUEST_USER_TURNS_REDIS_PREFIX,
    EMBED_GUEST_USER_TURNS_TTL_SECONDS,
)
from core.logging import get_logger
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.identity_models import User
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object
from core.ui_events.dispatcher import publish_ui_event_to_user
from core.utils.tokens import TokenData, TokenType

logger = get_logger(__name__)
JsonRpcId = str | int


def _embed_session_branch_from_token_metadata(metadata: JsonObject) -> str | None:
    b = metadata.get("embed_branch_id")
    if isinstance(b, str) and b.strip():
        return b.strip()
    return None


def _metadata_effective_branch(metadata: JsonObject | None) -> str | None:
    if metadata is None:
        return None
    b = metadata.get("branch")
    if b is not None and str(b).strip():
        return str(b).strip()
    return None


def _strict_json_rpc_id(raw_id: JsonValue) -> JsonRpcId | None:
    if raw_id is None:
        return None
    if isinstance(raw_id, bool):
        return None
    if isinstance(raw_id, (str, int)):
        return raw_id
    return None


def _require_json_rpc_id(raw_id: JsonValue) -> JsonRpcId:
    rpc_id = _strict_json_rpc_id(raw_id)
    if rpc_id is None:
        raise ValueError("Invalid Request: id must be string or integer")
    return rpc_id


def _string_list(raw: JsonValue | None) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _request_state_mapping(request: Request) -> Mapping[str, object]:
    raw_state = request.scope.get("state")
    if isinstance(raw_state, Mapping):
        return cast(Mapping[str, object], raw_state)
    return {}


def _get_user_groups(request: Request) -> list[str]:
    """Извлекает группы пользователя из request.state.user."""
    raw_user = _request_state_mapping(request).get("user")
    if raw_user is None:
        return []

    if isinstance(raw_user, User):
        return raw_user.groups

    user = require_json_object(raw_user, "request.state.user")
    groups = user.get("grps")
    if groups is None:
        groups = user.get("groups")
    return _string_list(groups)

router = APIRouter(tags=["public", "a2a"])


# Поддерживаемые A2A-методы
A2A_METHODS = {
    "message/send",
    "message/stream",
    "tasks/get",
    "tasks/cancel",
    "tasks/resubscribe",
    "tasks/pushNotificationConfig/get",
    "tasks/pushNotificationConfig/set",
    "tasks/pushNotificationConfig/delete",
    "tasks/pushNotificationConfig/list",
    "agent/getAuthenticatedExtendedCard",
}

_STREAM_METHODS = {"message/stream", "tasks/resubscribe"}
_EMBED_MESSAGE_METHODS = {"message/send", "message/stream"}
_EMBED_SESSION_METHODS = _EMBED_MESSAGE_METHODS | {"tasks/cancel"}
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}


def _is_embed_session_token(token_data: TokenData | None) -> bool:
    return token_data is not None and token_data.token_type == TokenType.EMBED_SESSION


_EMBED_GUEST_TURN_LUA = """
local raw = redis.call("GET", KEYS[1])
local cur = 0
if raw then cur = tonumber(raw) end
local maxn = tonumber(ARGV[2])
if cur >= maxn then
  return -1
end
local n = redis.call("INCR", KEYS[1])
if n == 1 then
  redis.call("EXPIRE", KEYS[1], tonumber(ARGV[1]))
end
return n
"""


def _a2a_message_context_id(params_dict: JsonObject) -> str:
    msg = params_dict.get("message")
    if not isinstance(msg, dict):
        return ""
    for key in ("contextId", "context_id"):
        v = msg.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


async def _embed_session_guest_turn_limit_error(
    *,
    container: FlowContainer,
    embed_target: EmbedTarget | None,
    method: str | None,
    params_dict: JsonObject,
) -> JsonObject | None:
    if method not in _EMBED_MESSAGE_METHODS:
        return None
    if embed_target is None or not embed_target.embed_id.strip():
        return None
    max_n = embed_target.guest_max_user_messages
    if max_n is None or max_n < 1:
        return None
    ctx_id = _a2a_message_context_id(params_dict)
    if not ctx_id:
        return {
            "code": -32000,
            "message": "Лимит embed-session действует только при непустом contextId в сообщении.",
        }
    key = f"{EMBED_GUEST_USER_TURNS_REDIS_PREFIX}:{embed_target.embed_id.strip()}:{ctx_id}"
    try:
        count_raw: JsonValue = await container.redis_client.eval(
            _EMBED_GUEST_TURN_LUA,
            1,
            key,
            str(EMBED_GUEST_USER_TURNS_TTL_SECONDS),
            str(max_n),
        )
    except Exception:
        logger.exception(
            "embed_guest_turn_limit_redis_failed",
            embed_id=embed_target.embed_id,
        )
        return {
            "code": -32000,
            "message": "Лимит сообщений временно недоступен. Попробуйте позже.",
        }
    try:
        if isinstance(count_raw, bool) or not isinstance(count_raw, (int, float, str)):
            raise ValueError("unexpected Redis EVAL response")
        n_turn = int(count_raw)
    except (TypeError, ValueError):
        logger.error(
            "embed_guest_turn_limit_bad_redis_reply",
            embed_id=embed_target.embed_id,
            count_raw=count_raw,
        )
        return {
            "code": -32000,
            "message": "Лимит сообщений временно недоступен. Попробуйте позже.",
        }
    if n_turn < 0:
        return {
            "code": -32000,
            "message": (
                "Достигнут лимит сообщений для этого виджета. Получите новый токен или обратитесь к владельцу."
            ),
        }
    return None


def _validate_embed_session_request(
    *,
    request: Request,
    token_data: TokenData,
    embed_id: str | None,
    flow_id: str,
    method: str,
    params_dict: JsonObject,
    expected_branch_id: str | None = None,
    expected_company_id: str | None = None,
) -> JsonObject | None:
    """Проверяет claims embed-session токена для A2A вызова."""
    metadata = token_data.metadata
    if expected_company_id is not None and token_data.company_id != expected_company_id:
        return {"code": -32000, "message": "Embed session token is not allowed for this company"}

    embed_token_id = metadata.get("embed_id")
    if embed_id is not None:
        if not isinstance(embed_token_id, str) or not embed_token_id.strip():
            return {"code": -32000, "message": "Invalid embed session token: embed_id is required"}
        if embed_token_id.strip() != embed_id:
            return {"code": -32000, "message": "Embed session token is not allowed for this embed"}

    embed_flow_id = metadata.get("embed_flow_id")
    if not isinstance(embed_flow_id, str) or not embed_flow_id.strip():
        return {"code": -32000, "message": "Invalid embed session token: embed_flow_id is required"}
    if flow_id != embed_flow_id.strip():
        return {"code": -32000, "message": "Embed session token is not allowed for this flow"}

    if method not in _EMBED_SESSION_METHODS:
        return {
            "code": -32000,
            "message": "Embed session token supports only message/send, message/stream and tasks/cancel",
        }

    allowed_origin = metadata.get("allowed_origin")
    origin = request.headers.get("origin", "")
    if isinstance(allowed_origin, str) and allowed_origin.strip():
        if origin != allowed_origin.strip():
            return {"code": -32000, "message": "Origin is not allowed for this embed session token"}

    allowed_branch_id = _embed_session_branch_from_token_metadata(metadata)
    if expected_branch_id is not None:
        if not isinstance(allowed_branch_id, str) or not allowed_branch_id.strip():
            return {"code": -32000, "message": "Invalid embed session token: embed_branch_id is required"}
        if allowed_branch_id.strip() != expected_branch_id:
            return {"code": -32000, "message": "Embed session token branch mismatch"}
    if method in _EMBED_MESSAGE_METHODS and isinstance(allowed_branch_id, str) and allowed_branch_id.strip():
        effective_branch_id = allowed_branch_id.strip()
        metadata_dict = params_dict.get("metadata")
        if metadata_dict is None:
            params_dict["metadata"] = {"branch": effective_branch_id}
        elif isinstance(metadata_dict, dict):
            request_branch = _metadata_effective_branch(metadata_dict)
            if request_branch is None:
                metadata_dict["branch"] = effective_branch_id
            elif request_branch != effective_branch_id:
                return {"code": -32000, "message": "Embed session token is not allowed for this branch"}
        else:
            return {"code": -32602, "message": "Invalid params: metadata must be object"}

    logger.info(
        "embed_session_validated flow_id=%s branch_id=%s company_id=%s origin=%s issuer=%s",
        flow_id,
        _embed_session_branch_from_token_metadata(metadata) or "default",
        token_data.company_id,
        origin,
        metadata.get("issued_by", "unknown"),
    )
    return None


def _sse_error_response(rpc_id: JsonRpcId | None, code: int, message: str) -> StreamingResponse:
    """JSON-RPC ошибка в виде SSE, чтобы клиент мог её распарсить."""
    error_payload = json.dumps(
        {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}},
        ensure_ascii=False,
    )

    async def _gen():
        yield f"data: {error_payload}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)


async def _get_flow_config(
    flow_id: str, container: FlowContainer, version: str | None = None,
) -> FlowConfig | None:
    """
    Получает конфигурацию агента.

    Аргументы:
        flow_id: ID агента
        container: DI-контейнер
        version: Версия агента (опционально). Если не указана - возвращает latest.
    """
    if version:
        return await container.flow_repository.get_version(flow_id, version)
    return await container.flow_repository.get(flow_id)


def _get_base_url(request: Request) -> str:
    return build_service_base_url(request, include_default_port=True)


@router.get("/{flow_id}/.well-known/agent-card.json")
async def get_agent_card_well_known(
    flow_id: str,
    request: Request,
    container: ContainerDep,
    v: str | None = None,
) -> JsonObject:
    """
    Agent Card по well-known URL.

    Параметры query:
        v: версия агента (опционально)
    """
    config = await _get_flow_config(flow_id, container, version=v)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    context = get_context()
    channel = A2AChannel(
        flow_id,
        context=context,
        flow_config=config,
        container=as_flow_runtime_container(container),
    )
    base_url = _get_base_url(request)
    try:
        return await channel.get_agent_card(base_url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{flow_id}")
async def get_agent_card(
    flow_id: str,
    request: Request,
    container: ContainerDep,
    v: str | None = None,
) -> JsonObject:
    """
    Agent Card по A2A спецификации - GET на URL агента.

    Параметры query:
        v: версия агента (опционально)
    """
    config = await _get_flow_config(flow_id, container, version=v)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    context = get_context()
    channel = A2AChannel(
        flow_id,
        context=context,
        flow_config=config,
        container=as_flow_runtime_container(container),
    )
    base_url = _get_base_url(request)
    try:
        return await channel.get_agent_card(base_url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _handle_streaming(
    handler: A2AChannel,
    params: MessageSendParams,
    rpc_id: JsonRpcId,
    context: JsonObject | None = None,
) -> AsyncGenerator[str, None]:
    try:
        async for event in handler.on_message_stream(params, context=context):
            event_data = event.model_dump(by_alias=True, exclude_none=True)
            response = {"jsonrpc": "2.0", "id": rpc_id, "result": event_data}
            yield f"data: {json.dumps(response, ensure_ascii=False, default=str)}\n\n"
    except PermissionDenied as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": e.error.to_json_rpc_error(),
        }
        yield f"data: {json.dumps(error_response, ensure_ascii=False, default=str)}\n\n"


async def _handle_resubscribe_streaming(
    handler: A2AChannel, params: TaskIdParams, rpc_id: JsonRpcId
) -> AsyncGenerator[str, None]:
    async for event in handler.on_resubscribe_to_task(params):
        event_data = event.model_dump(by_alias=True, exclude_none=True)
        response = {"jsonrpc": "2.0", "id": rpc_id, "result": event_data}
        yield f"data: {json.dumps(response, ensure_ascii=False, default=str)}\n\n"


async def _json_rpc_handler_internal(
    *,
    flow_id: str,
    request: Request,
    container: ContainerDep,
    v: str | None = None,
    embed_target: EmbedTarget | None = None,
):
    """
    JSON-RPC handler для A2A протокола.

    Версия агента может быть указана:
    - Query param: ?v=20241226120000000000
    - В metadata запроса: {"metadata": {"version": "20241226120000000000"}}
    """
    try:
        body = parse_json_object(await request.body(), "json_rpc.body")
    except json.JSONDecodeError as e:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
        )

    raw_rpc_id = body.get("id")
    response_id = _strict_json_rpc_id(raw_rpc_id)
    try:
        rpc_id = _require_json_rpc_id(raw_rpc_id)
    except ValueError as exc:
        return {
            "jsonrpc": "2.0",
            "id": response_id,
            "error": {"code": -32600, "message": str(exc)},
        }

    method_raw = body.get("method")
    if not isinstance(method_raw, str) or not method_raw.strip():
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32600, "message": "Invalid Request: missing 'method' field"},
        }
    method = method_raw.strip()

    _raw_params = body.get("params")
    if _raw_params is None:
        params_dict: JsonObject = {}
    elif isinstance(_raw_params, dict):
        params_dict = require_json_object(_raw_params, "params")
    else:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32602, "message": "Invalid params: expected object"},
        }

    token_data_raw = _request_state_mapping(request).get("token_data")
    token_data = token_data_raw if isinstance(token_data_raw, TokenData) else None
    if token_data is not None and _is_embed_session_token(token_data):
        embed_error = _validate_embed_session_request(
            request=request,
            token_data=token_data,
            embed_id=embed_target.embed_id if embed_target is not None else None,
            flow_id=flow_id,
            method=method,
            params_dict=params_dict,
            expected_branch_id=embed_target.branch_id if embed_target is not None else None,
            expected_company_id=embed_target.company_id if embed_target is not None else None,
        )
        if embed_error is not None:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": embed_error}

    if embed_target is not None and method in _EMBED_MESSAGE_METHODS:
        metadata_dict = params_dict.get("metadata")
        if metadata_dict is None:
            params_dict["metadata"] = {"branch": embed_target.branch_id}
        elif isinstance(metadata_dict, dict):
            request_branch = _metadata_effective_branch(metadata_dict)
            if request_branch is None:
                metadata_dict["branch"] = embed_target.branch_id
            elif request_branch != embed_target.branch_id:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32000, "message": "Embed config branch mismatch"},
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": "Invalid params: metadata must be object"},
            }

    if _is_embed_session_token(token_data) and isinstance(token_data, TokenData):
        lim_err = await _embed_session_guest_turn_limit_error(
            container=container,
            embed_target=embed_target,
            method=method,
            params_dict=params_dict,
        )
        if lim_err is not None:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": lim_err}

    # Версия: приоритет query param > metadata.version
    metadata_raw = params_dict.get("metadata")
    if metadata_raw is None:
        metadata: JsonObject = {}
    elif isinstance(metadata_raw, dict):
        metadata = require_json_object(metadata_raw, "params.metadata")
    else:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32602, "message": "Invalid params: metadata must be object"},
        }
    version_raw = metadata.get("version")
    if version_raw is not None and not isinstance(version_raw, str):
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32602, "message": "Invalid params: metadata.version must be string"},
        }
    version = v or version_raw

    config = await _get_flow_config(flow_id, container, version=version)
    if not config:
        version_info = f" version '{version}'" if version else ""
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000, "message": f"Flow not found: {flow_id}{version_info}"},
            }
        )

    if method not in A2A_METHODS:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    # Получаем Context из middleware (установлен при авторизации)
    context = get_context()

    handler = A2AChannel(
        flow_id,
        context=context,
        flow_config=config,
        container=as_flow_runtime_container(container),
    )

    # Группы пользователя для проверки прав доступа
    # 1. Из metadata (для тестов и внутренних вызовов)
    # 2. Из request.state.user (из JWT через middleware)
    user_groups_raw = metadata.get("__user_groups__")
    if user_groups_raw is None:
        user_groups = _get_user_groups(request)
    elif isinstance(user_groups_raw, list) and all(isinstance(item, str) for item in user_groups_raw):
        user_groups = user_groups_raw
    else:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32602, "message": "Invalid params: metadata.__user_groups__ must be string array"},
        }
    channel_context: JsonObject = {"user_groups": user_groups}

    # Добавляем groups в metadata для передачи в worker (для проверки прав доступа к tools)
    params_dict["metadata"] = metadata
    metadata["__user_groups__"] = user_groups

    try:
        if method == "message/send":
            params = MessageSendParams.model_validate(params_dict)
            result = await handler.on_message_send(params, context=channel_context)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "message/stream":
            params = MessageSendParams.model_validate(params_dict)
            return StreamingResponse(
                _handle_streaming(handler, params, rpc_id, channel_context),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        elif method == "tasks/get":
            params = TaskQueryParams.model_validate(params_dict)
            result = await handler.on_get_task(params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True) if result else None,
            }

        elif method == "tasks/cancel":
            params = TaskIdParams.model_validate(params_dict)
            result = await handler.on_cancel_task(params)
            if result is None:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32000, "message": "Task not found"},
                }
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "tasks/resubscribe":
            params = TaskIdParams.model_validate(params_dict)
            return StreamingResponse(
                _handle_resubscribe_streaming(handler, params, rpc_id),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        elif method == "tasks/pushNotificationConfig/get":
            params = GetTaskPushNotificationConfigParams.model_validate(params_dict)
            result = await handler.on_get_task_push_notification_config(params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True) if result else None,
            }

        elif method == "tasks/pushNotificationConfig/set":
            params = TaskPushNotificationConfig.model_validate(params_dict)
            result = await handler.on_set_task_push_notification_config(params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "tasks/pushNotificationConfig/delete":
            params = DeleteTaskPushNotificationConfigParams.model_validate(params_dict)
            await handler.on_delete_task_push_notification_config(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": None}

        elif method == "tasks/pushNotificationConfig/list":
            params = ListTaskPushNotificationConfigParams.model_validate(params_dict)
            result = await handler.on_list_task_push_notification_config(params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": [r.model_dump(by_alias=True, exclude_none=True) for r in result],
            }

        elif method == "agent/getAuthenticatedExtendedCard":
            base_url = _get_base_url(request)
            result = await handler.on_get_authenticated_extended_card(params_dict)
            if result:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": result.model_dump(by_alias=True, exclude_none=True),
                }
            card = await handler.get_agent_card(base_url)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": card,
            }

        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}

    except PermissionDenied as e:
        logger.warning(f"Permission denied for {method}: {e}")
        err = e.error.to_json_rpc_error()
        if method in _STREAM_METHODS:
            err_code = err.get("code", -32000)
            if isinstance(err_code, bool) or not isinstance(err_code, int):
                err_code = -32000
            err_message = err.get("message", str(e))
            if not isinstance(err_message, str):
                err_message = str(e)
            return _sse_error_response(rpc_id, err_code, err_message)
        return {"jsonrpc": "2.0", "id": rpc_id, "error": err}
    except Exception as e:
        logger.exception(f"Error handling {method}: {e}")
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, -32000, str(e))
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(e)}}


@router.post("/{flow_id}")
async def json_rpc_handler(
    flow_id: str,
    request: Request,
    container: ContainerDep,
    v: str | None = None,
):
    return await _json_rpc_handler_internal(
        flow_id=flow_id,
        request=request,
        container=container,
        v=v,
    )


@router.post("/embed/{embed_id}")
async def json_rpc_embed_handler(
    embed_id: str,
    request: Request,
    container: ContainerDep,
    v: str | None = None,
):
    embed_target = await resolve_embed_target(container, embed_id)
    if embed_target is None:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": f"Embed not found: {embed_id}"},
            },
            status_code=404,
        )
    if not embed_target.active:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": f"Embed disabled: {embed_id}"},
            },
            status_code=403,
        )
    return await _json_rpc_handler_internal(
        flow_id=embed_target.flow_id,
        request=request,
        container=container,
        v=v,
        embed_target=embed_target,
    )


@router.get("/{flow_id}/branches")
async def list_branches(flow_id: str, container: ContainerDep) -> list[JsonObject]:
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=as_flow_runtime_container(container))
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    return await channel.list_branches()


@router.get("/{flow_id}/branches/{branch_id}")
async def get_branch(flow_id: str, branch_id: str, container: ContainerDep) -> JsonObject:
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=as_flow_runtime_container(container))
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    result = await channel.get_branch(branch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Branch '{branch_id}' not found")
    return result


@router.get("/{flow_id}/branches/{branch_id}/tools")
async def get_branch_tools(flow_id: str, branch_id: str, container: ContainerDep) -> list[JsonObject]:
    """Получить список tools для ветки с полной информацией."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=as_flow_runtime_container(container))
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    # 'base' — это базовый агент без конкретной ветки
    if branch_id != "base":
        branch = await channel.get_branch(branch_id)
        if branch is None:
            raise HTTPException(status_code=404, detail=f"Branch '{branch_id}' not found")

    return await channel.get_branch_tools(branch_id)


@router.get("/{flow_id}/schema")
async def get_branch_schema(flow_id: str, container: ContainerDep) -> JsonObject:
    """Получить JSON Schema для создания ветки в формате ISchema."""
    _ = container
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=as_flow_runtime_container(container))
    try:
        return await channel.get_branch_schema()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{flow_id}/branches")
async def create_branch(
    flow_id: str,
    body: BranchCreateRequest,
    container: ContainerDep,
) -> JSONResponse:
    """Создать новую ветку."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=as_flow_runtime_container(container))
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    branch_id = body.branch_id

    try:
        result = await channel.create_branch(body)
    except ValueError as e:
        msg = str(e).lower()
        if "already exists" in msg or "уже существует" in msg:
            raise HTTPException(status_code=409, detail=str(e))
        raise HTTPException(status_code=400, detail=str(e))

    if context and context.user and context.user.user_id:
        await publish_ui_event_to_user(
            user_id=context.user.user_id,
            type="flows/branch/created",
            payload={"flow_id": flow_id, "branch_id": branch_id},
        )

    return JSONResponse(result, status_code=201)


@router.put("/{flow_id}/branches/{branch_id}")
async def update_branch(
    flow_id: str,
    branch_id: str,
    body: BranchUpdateRequest,
    container: ContainerDep,
) -> JsonObject:
    """Обновить существующую ветку."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=as_flow_runtime_container(container))
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        result = await channel.update_branch(branch_id, body)
    except ValueError as e:
        msg = str(e)
        if msg == f"Ветка '{branch_id}' не найдена":
            raise HTTPException(status_code=404, detail=f"Branch '{branch_id}' not found. Use POST to create.")
        raise HTTPException(status_code=400, detail=str(e))

    if context and context.user and context.user.user_id:
        await publish_ui_event_to_user(
            user_id=context.user.user_id,
            type="flows/branch/updated",
            payload={"flow_id": flow_id, "branch_id": branch_id},
        )

    return result


@router.delete("/{flow_id}/branches/{branch_id}")
async def delete_branch(flow_id: str, branch_id: str, container: ContainerDep) -> JsonObject:
    """Удалить ветку."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=as_flow_runtime_container(container))
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        result = await channel.delete_branch(branch_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if context and context.user and context.user.user_id:
        await publish_ui_event_to_user(
            user_id=context.user.user_id,
            type="flows/branch/deleted",
            payload={"flow_id": flow_id, "branch_id": branch_id},
        )

    return result
