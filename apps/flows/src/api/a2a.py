"""
HTTP и JSON-RPC эндпоинты A2A Protocol 1.0 для flows (protobuf / a2a-sdk 1.x).

Hard cut: только PascalCase методы из core.a2a.methods; 0.3 names → MethodNotFound.
"""

import hashlib
import json
from collections.abc import AsyncGenerator, Mapping
from typing import Literal, TypeVar, cast

from a2a.types import (
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    ListTaskPushNotificationConfigsRequest,
    ListTasksRequest,
    ListTasksResponse,
    Message,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskStatusUpdateEvent,
)
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.message import DecodeError
from google.protobuf.message import Message as ProtoMessage
from pydantic import BaseModel

from apps.flows.src.channels import PermissionDenied
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.durable_execution.repository import WorkflowProjectionMismatchError
from apps.flows.src.models import (
    BranchCreateRequest,
    BranchUpdateRequest,
    FlowConfig,
)
from apps.flows.src.services.embed_target_resolver import EmbedTarget, resolve_embed_target
from core.a2a import (
    A2A_ERROR_CODE_NAMES,
    A2A_METHODS,
    CANCEL_TASK,
    CREATE_TASK_PUSH_NOTIFICATION_CONFIG,
    DELETE_TASK_PUSH_NOTIFICATION_CONFIG,
    GET_EXTENDED_AGENT_CARD,
    GET_TASK,
    GET_TASK_PUSH_NOTIFICATION_CONFIG,
    LIST_TASK_PUSH_NOTIFICATION_CONFIGS,
    LIST_TASKS,
    SEND_MESSAGE,
    SEND_STREAMING_MESSAGE,
    SUBSCRIBE_TO_TASK,
    A2AApplicationError,
    A2AErrorCode,
)
from core.a2a.codec import stream_response_from_event, stream_response_to_json_dict
from core.a2a.extensions import (
    A2A_EXTENSIONS_HEADER,
    A2UI_EXTENSION_URI,
    A2UI_PLATFORM_CATALOG_ID,
    A2UI_VERSION,
    extract_subscribe_after_sequence,
    parse_a2a_extensions_header,
    strip_subscribe_platform_metadata,
)
from core.context import get_context
from core.events import publish_event_to_user
from core.identity.embed_guest_turns import (
    EMBED_GUEST_USER_TURNS_REDIS_PREFIX,
    EMBED_GUEST_USER_TURNS_TTL_SECONDS,
    EMBED_SESSION_ID_METADATA_KEY,
)
from core.logging import get_logger
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.embed_models import EmbedInterfaceLook
from core.models.flow_interface import (
    apply_embed_interface_override,
    resolve_flow_interface_config,
)
from core.models.identity_models import User
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object
from core.utils.tokens import TokenData, TokenType

logger = get_logger(__name__)
JsonRpcId = str | int

A2A_PROTOCOL_VERSION = "1.0"
A2A_VERSION_HEADER = "A2A-Version"


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

_STREAM_METHODS = frozenset({SEND_STREAMING_MESSAGE, SUBSCRIBE_TO_TASK})
_EMBED_MESSAGE_METHODS = frozenset({SEND_MESSAGE, SEND_STREAMING_MESSAGE})
# Flow UI hydrate/reconnect needs task-read methods on both scoped guest tokens.
_SCOPED_SESSION_A2A_METHODS = _EMBED_MESSAGE_METHODS | {
    GET_TASK,
    LIST_TASKS,
    SUBSCRIBE_TO_TASK,
    CANCEL_TASK,
}
_EMBED_SESSION_METHODS = _SCOPED_SESSION_A2A_METHODS
_FLOW_UI_SHARE_METHODS = _SCOPED_SESSION_A2A_METHODS
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
}


def _a2a_rpc_error(code: A2AErrorCode, message: str | None = None) -> JsonObject:
    return {
        "code": int(code),
        "message": message if message is not None else A2A_ERROR_CODE_NAMES[code],
    }


_TProto = TypeVar("_TProto", bound=ProtoMessage)


def _proto_result(message: ProtoMessage) -> JsonObject:
    payload = require_json_object(MessageToDict(message), "a2a.result")
    # ProtoJSON опускает пустые string; ListTasks.next_page_token REQUIRED (может быть "").
    if isinstance(message, ListTasksResponse) and "nextPageToken" not in payload:
        payload["nextPageToken"] = ""
    return payload


def _stream_response_result(
    event: Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent,
) -> JsonObject:
    return stream_response_to_json_dict(stream_response_from_event(event))


def _parse_proto_params(params_dict: JsonObject, proto_cls: type[_TProto]) -> _TProto:
    message = proto_cls()
    try:
        _ = ParseDict(dict(params_dict), message)
    except (DecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid params for {proto_cls.__name__}: {exc}") from exc
    return message


def _check_a2a_version(request: Request) -> JsonObject | None:
    """A2A-Version: принимается только \"1.0\"; любое другое значение → -32009.

    Отсутствующий header допускается как implicit 1.0 (платформенные клиенты);
    не-1.0 значения отклоняются жёстко.
    """
    raw = request.headers.get(A2A_VERSION_HEADER)
    if raw is None:
        return None
    if raw.strip() != A2A_PROTOCOL_VERSION:
        return _a2a_rpc_error(
            A2AErrorCode.VERSION_NOT_SUPPORTED,
            f"Supported A2A-Version: {A2A_PROTOCOL_VERSION}",
        )
    return None


def _is_embed_session_token(token_data: TokenData | None) -> bool:
    return token_data is not None and token_data.token_type == TokenType.EMBED_SESSION


def _is_flow_ui_share_token(token_data: TokenData | None) -> bool:
    return token_data is not None and token_data.token_type == TokenType.FLOW_UI_SHARE


def _validate_flow_ui_share_claims(
    *,
    request: Request,
    token_data: TokenData,
    flow_id: str,
    branch_id: str | None = None,
) -> str | None:
    metadata = token_data.metadata
    expected: dict[str, set[str] | None] = {
        "flow_ui_share_grant_id": None,
        "flow_ui_share_permission": {"view", "interact"},
        "flow_ui_share_flow_id": None,
        "flow_ui_share_branch_id": None,
        "flow_ui_share_context_id": None,
        "flow_ui_share_document_id": None,
        "flow_ui_share_origin": None,
    }
    for key, allowed in expected.items():
        value = metadata.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"Invalid Flow UI share token: {key} is required"
        if allowed is not None and value not in allowed:
            return f"Invalid Flow UI share token: {key} is invalid"
    if metadata["flow_ui_share_flow_id"] != flow_id:
        return "Flow UI share token is not allowed for this flow"
    if branch_id is not None and metadata["flow_ui_share_branch_id"] != branch_id:
        return "Flow UI share token is not allowed for this branch"
    request_origin = (
        request.headers.get("origin", "").strip()
        or build_service_base_url(request).rstrip("/")
    )
    if request_origin != metadata["flow_ui_share_origin"]:
        return "Origin is not allowed for this Flow UI share token"
    return None


def _validate_flow_ui_share_request(
    *,
    request: Request,
    token_data: TokenData,
    flow_id: str,
    method: str,
    params_dict: JsonObject,
) -> JsonObject | None:
    claims_error = _validate_flow_ui_share_claims(
        request=request,
        token_data=token_data,
        flow_id=flow_id,
    )
    if claims_error is not None:
        return {"code": -32000, "message": claims_error}
    if method not in _FLOW_UI_SHARE_METHODS:
        return {
            "code": -32000,
            "message": "Flow UI share token cannot access this A2A method",
        }
    if method in _EMBED_MESSAGE_METHODS:
        context_id = _a2a_message_context_id(params_dict)
        if context_id != token_data.metadata["flow_ui_share_context_id"]:
            return {"code": -32000, "message": "Flow UI share context mismatch"}
        metadata_raw = params_dict.get("metadata")
        if metadata_raw is None:
            params_dict["metadata"] = {
                "branch": token_data.metadata["flow_ui_share_branch_id"]
            }
        elif isinstance(metadata_raw, dict):
            requested = _metadata_effective_branch(metadata_raw)
            expected_branch = token_data.metadata["flow_ui_share_branch_id"]
            if requested is None:
                metadata_raw["branch"] = expected_branch
            elif requested != expected_branch:
                return {"code": -32000, "message": "Flow UI share branch mismatch"}
        else:
            return {"code": -32602, "message": "Invalid params: metadata must be object"}
    return None


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


def _list_tasks_context_id(params_dict: JsonObject) -> str:
    for key in ("contextId", "context_id"):
        value = params_dict.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _embed_session_limit_subject(token_data: TokenData, params_dict: JsonObject) -> str:
    raw_session_id = token_data.metadata.get(EMBED_SESSION_ID_METADATA_KEY)
    if isinstance(raw_session_id, str) and raw_session_id.strip():
        return f"sid:{raw_session_id.strip()}"
    if token_data.user_id.strip():
        return f"user:{token_data.user_id.strip()}"
    ctx_id = _a2a_message_context_id(params_dict)
    if ctx_id:
        return f"ctx:{ctx_id}"
    return ""


def _turn_limit_key_part(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


async def _embed_session_guest_turn_limit_error(
    *,
    container: FlowContainer,
    embed_target: EmbedTarget | None,
    token_data: TokenData,
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
    subject = _embed_session_limit_subject(token_data, params_dict)
    if not subject:
        return {
            "code": -32000,
            "message": "Invalid embed session token: stable session id is required",
        }
    key = (
        f"{EMBED_GUEST_USER_TURNS_REDIS_PREFIX}:"
        f"{embed_target.embed_id.strip()}:{_turn_limit_key_part(subject)}"
    )
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


def _validate_embed_session_claims(
    *,
    request: Request,
    token_data: TokenData,
    embed_id: str | None,
    flow_id: str,
    expected_branch_id: str | None = None,
    expected_company_id: str | None = None,
) -> str | None:
    """Проверяет базовые claims embed-session токена (company/embed/flow/origin/branch)."""
    metadata = token_data.metadata
    if expected_company_id is not None and token_data.company_id != expected_company_id:
        return "Embed session token is not allowed for this company"

    embed_token_id = metadata.get("embed_id")
    if embed_id is not None:
        if not isinstance(embed_token_id, str) or not embed_token_id.strip():
            return "Invalid embed session token: embed_id is required"
        if embed_token_id.strip() != embed_id:
            return "Embed session token is not allowed for this embed"

    embed_flow_id = metadata.get("embed_flow_id")
    if not isinstance(embed_flow_id, str) or not embed_flow_id.strip():
        return "Invalid embed session token: embed_flow_id is required"
    if flow_id != embed_flow_id.strip():
        return "Embed session token is not allowed for this flow"

    allowed_origin = metadata.get("allowed_origin")
    origin = request.headers.get("origin", "")
    if isinstance(allowed_origin, str) and allowed_origin.strip():
        if origin != allowed_origin.strip():
            return "Origin is not allowed for this embed session token"

    allowed_branch_id = _embed_session_branch_from_token_metadata(metadata)
    if expected_branch_id is not None:
        if not isinstance(allowed_branch_id, str) or not allowed_branch_id.strip():
            return "Invalid embed session token: embed_branch_id is required"
        if allowed_branch_id.strip() != expected_branch_id:
            return "Embed session token branch mismatch"
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
    claims_error = _validate_embed_session_claims(
        request=request,
        token_data=token_data,
        embed_id=embed_id,
        flow_id=flow_id,
        expected_branch_id=expected_branch_id,
        expected_company_id=expected_company_id,
    )
    if claims_error is not None:
        return {"code": -32000, "message": claims_error}

    if method not in _EMBED_SESSION_METHODS:
        return {
            "code": -32000,
            "message": "Embed session token cannot access this A2A method",
        }

    if method == LIST_TASKS:
        if not _list_tasks_context_id(params_dict):
            return {
                "code": -32000,
                "message": "Embed session ListTasks requires contextId",
            }

    allowed_branch_id = _embed_session_branch_from_token_metadata(metadata)
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
        request.headers.get("origin", ""),
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
    params: SendMessageRequest,
    rpc_id: JsonRpcId,
    context: JsonObject | None = None,
) -> AsyncGenerator[str, None]:
    try:
        async for event in handler.on_message_stream(params, context=context):
            response = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": _stream_response_result(event),
            }
            yield f"data: {json.dumps(response, ensure_ascii=False, default=str)}\n\n"
    except PermissionDenied as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": e.error.to_json_rpc_error(),
        }
        yield f"data: {json.dumps(error_response, ensure_ascii=False, default=str)}\n\n"


async def _handle_subscribe_streaming(
    handler: A2AChannel,
    params: SubscribeToTaskRequest,
    rpc_id: JsonRpcId,
    *,
    after_sequence: int,
) -> AsyncGenerator[str, None]:
    async for event in handler.on_subscribe_to_task(params, after_sequence=after_sequence):
        response = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": _stream_response_result(event),
        }
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

    version_error = _check_a2a_version(request)
    if version_error is not None:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": version_error}

    if method not in A2A_METHODS:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

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

    if token_data is not None and _is_flow_ui_share_token(token_data):
        share_error = _validate_flow_ui_share_request(
            request=request,
            token_data=token_data,
            flow_id=flow_id,
            method=method,
            params_dict=params_dict,
        )
        if share_error is not None:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": share_error}

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
            token_data=token_data,
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

    # Получаем Context из middleware (установлен при авторизации)
    context = get_context()

    handler = A2AChannel(
        flow_id,
        context=context,
        flow_config=config,
        container=as_flow_runtime_container(container),
        activated_extensions=parse_a2a_extensions_header(
            request.headers.get(A2A_EXTENSIONS_HEADER)
        ),
        interface_override=(
            None if embed_target is None else embed_target.interface_override
        ),
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

    # metadata + __user_groups__ только в params методов с MessageSendParams
    # (protobuf GetTask/CancelTask/ListTasks metadata не имеют — ParseDict fail-closed).
    metadata["__user_groups__"] = user_groups
    if method in (SEND_MESSAGE, SEND_STREAMING_MESSAGE):
        params_dict["metadata"] = metadata

    try:
        if method == SEND_MESSAGE:
            params = _parse_proto_params(params_dict, SendMessageRequest)
            if not params.HasField("message"):
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32602, "message": "Invalid params: message is required"},
                }
            result = await handler.on_message_send(params, context=channel_context)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)}

        if method == SEND_STREAMING_MESSAGE:
            params = _parse_proto_params(params_dict, SendMessageRequest)
            if not params.HasField("message"):
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": -32602, "message": "Invalid params: message is required"},
                }
            return StreamingResponse(
                _handle_streaming(handler, params, rpc_id, channel_context),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        if method == GET_TASK:
            params = _parse_proto_params(params_dict, GetTaskRequest)
            result = await handler.on_get_task(params)
            if result is None:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": _a2a_rpc_error(A2AErrorCode.TASK_NOT_FOUND),
                }
            return {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)}

        if method == LIST_TASKS:
            params = _parse_proto_params(params_dict, ListTasksRequest)
            result = await handler.on_list_tasks(params, context=channel_context)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)}

        if method == CANCEL_TASK:
            params = _parse_proto_params(params_dict, CancelTaskRequest)
            result = await handler.on_cancel_task(params)
            if result is None:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": _a2a_rpc_error(A2AErrorCode.TASK_NOT_FOUND),
                }
            return {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)}

        if method == SUBSCRIBE_TO_TASK:
            after_sequence = extract_subscribe_after_sequence(params_dict)
            params = _parse_proto_params(
                strip_subscribe_platform_metadata(params_dict),
                SubscribeToTaskRequest,
            )
            return StreamingResponse(
                _handle_subscribe_streaming(
                    handler,
                    params,
                    rpc_id,
                    after_sequence=after_sequence,
                ),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        if method == GET_TASK_PUSH_NOTIFICATION_CONFIG:
            params = _parse_proto_params(
                params_dict, GetTaskPushNotificationConfigRequest
            )
            result = await handler.on_get_task_push_notification_config(params)
            if result is None:
                return {"jsonrpc": "2.0", "id": rpc_id, "result": None}
            return {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)}

        if method == CREATE_TASK_PUSH_NOTIFICATION_CONFIG:
            params = _parse_proto_params(params_dict, TaskPushNotificationConfig)
            result = await handler.on_create_task_push_notification_config(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)}

        if method == DELETE_TASK_PUSH_NOTIFICATION_CONFIG:
            params = _parse_proto_params(
                params_dict, DeleteTaskPushNotificationConfigRequest
            )
            await handler.on_delete_task_push_notification_config(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": None}

        if method == LIST_TASK_PUSH_NOTIFICATION_CONFIGS:
            params = _parse_proto_params(
                params_dict, ListTaskPushNotificationConfigsRequest
            )
            result = await handler.on_list_task_push_notification_configs(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)}

        if method == GET_EXTENDED_AGENT_CARD:
            # extended_agent_card=false на AgentCard — без silent fallback на regular card.
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": _a2a_rpc_error(A2AErrorCode.EXTENDED_AGENT_CARD_NOT_CONFIGURED),
            }

        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    except ValueError as e:
        logger.warning(f"Invalid params for {method}: {e}")
        err = {"code": -32602, "message": str(e)}
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, -32602, str(e))
        return {"jsonrpc": "2.0", "id": rpc_id, "error": err}
    except A2AApplicationError as e:
        logger.warning(f"A2A application error for {method}: {e}")
        err = e.to_json_rpc_error()
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, int(e.code), e.message)
        return {"jsonrpc": "2.0", "id": rpc_id, "error": err}
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
    except WorkflowProjectionMismatchError as e:
        logger.error(
            "workflow_projection_mismatch",
            session_id=e.session_id,
            expected_hash=e.expected_hash,
            computed_hash=e.computed_hash,
        )
        projection_error = {
            "code": -32051,
            "message": str(e),
            "data": {
                "error_code": "projection_hash_mismatch",
                "session_id": e.session_id,
                "expected_hash": e.expected_hash,
                "computed_hash": e.computed_hash,
            },
        }
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, -32051, str(e))
        return {"jsonrpc": "2.0", "id": rpc_id, "error": projection_error}
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


class InterfaceProfileViewer(BaseModel):
    """Control-plane permissions; runtime state is intentionally absent."""

    can_edit_flow: bool
    can_interact: bool
    can_share: bool
    auth_mode: Literal["platform", "embed", "share"]


class InterfaceCatalogProfile(BaseModel):
    extension_uri: str = A2UI_EXTENSION_URI
    version: str = A2UI_VERSION
    platform_catalog_id: str = A2UI_PLATFORM_CATALOG_ID


class InterfaceCapabilitiesProfile(BaseModel):
    bootstrap: bool = True
    autosync: bool = True
    cancel: bool
    files: bool
    voice: bool


class InterfaceFlowIdentity(BaseModel):
    title: str
    image_url: str | None = None


class InterfaceProfileResponse(BaseModel):
    """Narrow control plane; document, values and artifacts travel only in A2A."""

    flow_id: str
    branch_id: str
    viewer: InterfaceProfileViewer
    look: EmbedInterfaceLook | None = None
    catalog: InterfaceCatalogProfile
    capabilities: InterfaceCapabilitiesProfile
    flow_identity: InterfaceFlowIdentity


async def _interface_profile_internal(
    *,
    flow_id: str,
    branch_id: str,
    request: Request,
    container: FlowContainer,
    embed_target: EmbedTarget | None = None,
) -> InterfaceProfileResponse:
    """Resolve host controls without exposing a second runtime UI representation."""
    config = await _get_flow_config(flow_id, container)
    if config is None:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    if embed_target is None and config.branches and branch_id != "default":
        if branch_id not in config.branches:
            raise HTTPException(status_code=404, detail=f"Branch '{branch_id}' not found")

    token_data_raw = _request_state_mapping(request).get("token_data")
    token_data = token_data_raw if isinstance(token_data_raw, TokenData) else None
    is_embed_session = _is_embed_session_token(token_data)
    is_share_session = _is_flow_ui_share_token(token_data)
    if is_embed_session and isinstance(token_data, TokenData):
        claims_error = _validate_embed_session_claims(
            request=request,
            token_data=token_data,
            embed_id=embed_target.embed_id if embed_target is not None else None,
            flow_id=flow_id,
            expected_branch_id=embed_target.branch_id if embed_target is not None else None,
            expected_company_id=embed_target.company_id if embed_target is not None else None,
        )
        if claims_error is not None:
            raise HTTPException(status_code=403, detail=claims_error)

    share_permission: str | None = None
    if is_share_session and isinstance(token_data, TokenData):
        claims_error = _validate_flow_ui_share_claims(
            request=request,
            token_data=token_data,
            flow_id=flow_id,
            branch_id=branch_id,
        )
        if claims_error is not None:
            raise HTTPException(status_code=403, detail=claims_error)
        try:
            grant = await container.flow_ui_share_service.authorize(
                grant_id=str(token_data.metadata["flow_ui_share_grant_id"]),
                company_id=token_data.company_id,
                flow_id=flow_id,
                context_id=str(token_data.metadata["flow_ui_share_context_id"]),
                document_id=str(token_data.metadata["flow_ui_share_document_id"]),
                require_interact=False,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        share_permission = grant.permission

    branch = config.branches.get(branch_id)
    effective_interface = resolve_flow_interface_config(
        config.interface,
        branch_override=None if branch is None else branch.interface_override,
    )
    effective_interface = apply_embed_interface_override(
        effective_interface,
        None if embed_target is None else embed_target.interface_override,
    )
    policy = effective_interface.policy
    look = embed_target.look if embed_target is not None else None
    return InterfaceProfileResponse(
        flow_id=flow_id,
        branch_id=branch_id,
        viewer=InterfaceProfileViewer(
            can_edit_flow=not is_embed_session and not is_share_session,
            can_interact=share_permission != "view",
            can_share=(
                not is_share_session
                and (
                    not is_embed_session
                    or (look is not None and look.session_share_enabled)
                )
            ),
            auth_mode=(
                "share"
                if is_share_session
                else "embed"
                if is_embed_session
                else "platform"
            ),
        ),
        look=look,
        catalog=InterfaceCatalogProfile(),
        capabilities=InterfaceCapabilitiesProfile(
            autosync=share_permission != "view",
            cancel=policy.allow_cancel and share_permission != "view",
            files=policy.show_files_panel and not is_share_session,
            voice=(
                policy.allow_voice
                and share_permission != "view"
                and (look is None or look.voice_enabled)
            ),
        ),
        flow_identity=InterfaceFlowIdentity(
            title=config.name,
            image_url=config.store_card_image_url,
        ),
    )


@router.get("/{flow_id}/interface-profile", response_model=InterfaceProfileResponse)
async def get_flow_interface_profile(
    flow_id: str,
    request: Request,
    container: ContainerDep,
    branch_id: str = "default",
) -> InterfaceProfileResponse:
    """Control plane for an authenticated platform surface."""
    return await _interface_profile_internal(
        flow_id=flow_id,
        branch_id=branch_id,
        request=request,
        container=container,
    )


@router.get("/embed/{embed_id}/interface-profile", response_model=InterfaceProfileResponse)
async def get_embed_interface_profile(
    embed_id: str,
    request: Request,
    container: ContainerDep,
) -> InterfaceProfileResponse:
    """Control plane for an embed surface; runtime document still comes from A2A."""
    embed_target = await resolve_embed_target(container, embed_id)
    if embed_target is None:
        raise HTTPException(status_code=404, detail=f"Embed not found: {embed_id}")
    if not embed_target.active:
        raise HTTPException(status_code=403, detail=f"Embed disabled: {embed_id}")
    return await _interface_profile_internal(
        flow_id=embed_target.flow_id,
        branch_id=embed_target.branch_id,
        request=request,
        container=container,
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
        await publish_event_to_user(
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
        await publish_event_to_user(
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
        await publish_event_to_user(
            user_id=context.user.user_id,
            type="flows/branch/deleted",
            payload={"flow_id": flow_id, "branch_id": branch_id},
        )

    return result
