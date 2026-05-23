"""
HTTP и JSON-RPC эндпоинты A2A для flows (a2a-sdk).
Полная реализация протокола; поддержаны все методы спецификации.
"""

import json
from typing import Any

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
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import FlowConfig
from apps.flows.src.services.embed_target_resolver import EmbedTarget, resolve_embed_target
from core.context import get_context
from core.identity.embed_guest_turns import (
    EMBED_GUEST_USER_TURNS_REDIS_PREFIX,
    EMBED_GUEST_USER_TURNS_TTL_SECONDS,
)
from core.logging import get_logger
from core.ui_events.dispatcher import publish_ui_event_to_user
from core.utils.tokens import TokenData, TokenType

logger = get_logger(__name__)
JsonDict = dict[str, Any]
JsonRpcId = str | int


def _embed_session_branch_from_token_metadata(metadata: dict[str, Any]) -> str | None:
    if not isinstance(metadata, dict):
        return None
    b = metadata.get("embed_branch_id")
    if isinstance(b, str) and b.strip():
        return b.strip()
    return None


def _metadata_effective_branch(metadata: dict[str, Any] | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    b = metadata.get("branch")
    if b is not None and str(b).strip():
        return str(b).strip()
    return None


def _strict_json_rpc_id(raw_id: Any) -> JsonRpcId | None:
    if raw_id is None:
        return None
    if isinstance(raw_id, bool):
        return None
    if isinstance(raw_id, (str, int)):
        return raw_id
    return None


def _require_json_rpc_id(raw_id: Any) -> JsonRpcId:
    rpc_id = _strict_json_rpc_id(raw_id)
    if rpc_id is None:
        raise ValueError("Invalid Request: id must be string or integer")
    return rpc_id


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _get_user_groups(request: Request) -> list[str]:
    """Извлекает группы пользователя из request.state.user."""
    if not hasattr(request.state, "user") or request.state.user is None:
        return []

    user = request.state.user
    if isinstance(user, dict):
        groups = user.get("grps")
        if groups is None:
            groups = user.get("groups")
        return _string_list(groups)

    groups = getattr(user, "grps", None)
    if groups is None:
        groups = getattr(user, "groups", None)
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


def _a2a_message_context_id(params_dict: dict[str, Any]) -> str:
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
    token_data: TokenData,
    embed_target: EmbedTarget | None,
    method: str | None,
    params_dict: dict[str, Any],
) -> dict[str, Any] | None:
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
        count_raw = await container.redis_client.eval(
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
    params_dict: dict[str, Any],
    expected_branch_id: str | None = None,
    expected_company_id: str | None = None,
) -> dict[str, Any] | None:
    """Проверяет claims embed-session токена для A2A вызова."""
    metadata = token_data.metadata if isinstance(token_data.metadata, dict) else {}
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

    Args:
        flow_id: ID агента
        container: DI-контейнер
        version: Версия агента (опционально). Если не указана - возвращает latest.
    """
    if version:
        return await container.flow_repository.get_version(flow_id, version)
    return await container.flow_repository.get(flow_id)


def _get_base_url(request: Request) -> str:
    """Получает базовый URL из request с приоритетом X-Forwarded-Proto."""
    # Приоритет X-Forwarded-Proto над request.url.scheme
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto:
        scheme = forwarded_proto.lower()
    else:
        scheme = request.url.scheme

    # Используем X-Forwarded-Host, который содержит host:port от Nginx
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        host = forwarded_host
    else:
        host = request.headers.get("host") or request.url.netloc
        # Если host не содержит порт, добавляем порт
        if ":" not in host:
            if request.url.port:
                host = f"{host}:{request.url.port}"
            elif scheme == "https":
                host = f"{host}:443"
            elif scheme == "http":
                host = f"{host}:80"

    return f"{scheme}://{host}"


@router.get("/{flow_id}/.well-known/agent-card.json")
async def get_agent_card_well_known(
    flow_id: str,
    request: Request,
    container: ContainerDep,
    v: str | None = None,
) -> dict[str, Any]:
    """
    Agent Card по well-known URL.

    Query params:
        v: версия агента (опционально)
    """
    config = await _get_flow_config(flow_id, container, version=v)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    context = get_context()
    channel = A2AChannel(flow_id, context=context, flow_config=config, container=container)
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
) -> dict[str, Any]:
    """
    Agent Card по A2A спецификации - GET на URL агента.

    Query params:
        v: версия агента (опционально)
    """
    config = await _get_flow_config(flow_id, container, version=v)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    context = get_context()
    channel = A2AChannel(flow_id, context=context, flow_config=config, container=container)
    base_url = _get_base_url(request)
    try:
        return await channel.get_agent_card(base_url)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _handle_streaming(
    handler: A2AChannel,
    params: MessageSendParams,
    rpc_id: JsonRpcId,
    context: JsonDict | None = None,
):
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
):
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
        body = await request.json()
    except json.JSONDecodeError as e:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
        )

    if not isinstance(body, dict):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request: expected JSON object"},
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
        params_dict: dict[str, Any] = {}
    elif isinstance(_raw_params, dict):
        params_dict = dict(_raw_params)
    else:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32602, "message": "Invalid params: expected object"},
        }

    token_data = getattr(request.state, "token_data", None)
    if _is_embed_session_token(token_data):
        if not isinstance(token_data, TokenData):
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32000, "message": "Invalid embed session token"},
            }
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
            token_data=token_data,
            embed_target=embed_target,
            method=method,
            params_dict=params_dict,
        )
        if lim_err is not None:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": lim_err}

    # Версия: приоритет query param > metadata.version
    metadata_raw = params_dict.get("metadata")
    if metadata_raw is None:
        metadata: JsonDict = {}
    elif isinstance(metadata_raw, dict):
        metadata = metadata_raw
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

    handler = A2AChannel(flow_id, context=context, flow_config=config, container=container)

    # Группы пользователя для проверки permissions
    # 1. Из metadata (для тестов и internal calls)
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
    channel_context: JsonDict = {"user_groups": user_groups}

    # Добавляем groups в metadata для передачи в worker (для проверки permissions на tools)
    params_dict["metadata"] = metadata
    metadata["__user_groups__"] = user_groups

    try:
        if method == "message/send":
            params = MessageSendParams(**params_dict)
            result = await handler.on_message_send(params, context=channel_context)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "message/stream":
            params = MessageSendParams(**params_dict)
            return StreamingResponse(
                _handle_streaming(handler, params, rpc_id, channel_context),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        elif method == "tasks/get":
            params = TaskQueryParams(**params_dict)
            result = await handler.on_get_task(params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True) if result else None,
            }

        elif method == "tasks/cancel":
            params = TaskIdParams(**params_dict)
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
            params = TaskIdParams(**params_dict)
            return StreamingResponse(
                _handle_resubscribe_streaming(handler, params, rpc_id),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        elif method == "tasks/pushNotificationConfig/get":
            params = GetTaskPushNotificationConfigParams(**params_dict)
            result = await handler.on_get_task_push_notification_config(params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True) if result else None,
            }

        elif method == "tasks/pushNotificationConfig/set":
            params = TaskPushNotificationConfig(**params_dict)
            result = await handler.on_set_task_push_notification_config(params)
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result.model_dump(by_alias=True, exclude_none=True),
            }

        elif method == "tasks/pushNotificationConfig/delete":
            params = DeleteTaskPushNotificationConfigParams(**params_dict)
            await handler.on_delete_task_push_notification_config(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": None}

        elif method == "tasks/pushNotificationConfig/list":
            params = ListTaskPushNotificationConfigParams(**params_dict)
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
            return _sse_error_response(rpc_id, err.get("code", -32000), err.get("message", str(e)))
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
async def list_branches(flow_id: str, container: ContainerDep) -> list[dict[str, Any]]:
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    return await channel.list_branches()


@router.get("/{flow_id}/branches/{branch_id}")
async def get_branch(flow_id: str, branch_id: str, container: ContainerDep) -> dict[str, Any]:
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    result = await channel.get_branch(branch_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Branch '{branch_id}' not found")
    return result


@router.get("/{flow_id}/branches/{branch_id}/tools")
async def get_branch_tools(flow_id: str, branch_id: str, container: ContainerDep) -> list[dict[str, Any]]:
    """Получить список tools для ветки с полной информацией."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
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
async def get_branch_schema(flow_id: str, container: ContainerDep) -> dict[str, Any]:
    """Получить JSON Schema для создания ветки в формате ISchema."""
    _ = container
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
    try:
        return await channel.get_branch_schema()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{flow_id}/branches")
async def create_branch(flow_id: str, request: Request, container: ContainerDep) -> JSONResponse:
    """Создать новую ветку."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    branch_id = data.get("branch_id")
    if not branch_id:
        raise HTTPException(status_code=400, detail="Field 'branch_id' is required")

    try:
        result = await channel.create_branch(branch_id, data)
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
async def update_branch(flow_id: str, branch_id: str, request: Request, container: ContainerDep) -> dict[str, Any]:
    """Обновить существующую ветку."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
    config = await _get_flow_config(flow_id, container)
    if not config:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        result = await channel.update_branch(branch_id, data)
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
async def delete_branch(flow_id: str, branch_id: str, container: ContainerDep) -> dict[str, Any]:
    """Удалить ветку."""
    context = get_context()
    channel = A2AChannel(flow_id, context=context, container=container)
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
