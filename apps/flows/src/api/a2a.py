"""
HTTP и JSON-RPC эндпоинты A2A Protocol 1.0 для flows (protobuf / a2a-sdk 1.x).

Hard cut: только PascalCase методы из core.a2a.methods; 0.3 names → MethodNotFound.
"""

import hashlib
import json
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import TypeVar, cast

from a2a.types import (
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    ListTaskPushNotificationConfigsRequest,
    ListTasksRequest,
    Message,
    SendMessageRequest,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskStatusUpdateEvent,
)
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from google.protobuf.json_format import ParseDict
from google.protobuf.message import DecodeError
from google.protobuf.message import Message as ProtoMessage

from apps.flows.di import Di
from apps.flows.src.channels import PermissionDenied
from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.channels.factory import get_channel
from apps.flows.src.durable_execution.models import WorkflowProjectionMismatchError
from apps.flows.src.models import FlowConfig
from apps.flows.src.models.bundle_registry import FlowBundleRegistry
from apps.flows.src.services.embed_target_resolver import EmbedTarget, resolve_embed_target
from apps.flows.src.services.flows_loader import FlowsLoader
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
    rpc_result_to_json_dict,
)
from core.a2a.codec import stream_response_from_event, stream_response_to_json_dict
from core.authz.models import AuthzObject
from core.context import get_context, require_active_company, require_context
from core.identity.embed_guest_turns import (
    EMBED_GUEST_USER_TURNS_REDIS_PREFIX,
    EMBED_GUEST_USER_TURNS_TTL_SECONDS,
    EMBED_SESSION_ID_METADATA_KEY,
)
from core.logging import get_logger
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.context_models import Context
from core.models.identity_models import User
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    parse_yaml_value,
    require_json_object,
)
from core.ui_document.interface import (
    FlowInterfaceCapabilities,
    FlowInterfaceIdentity,
    FlowInterfaceResponse,
    FlowInterfaceViewer,
)
from core.utils.tokens import TokenData, TokenType
from core.websocket import WsCommandError, raise_forbidden, raise_not_found

logger = get_logger(__name__)
JsonRpcId = str | int

A2A_PROTOCOL_VERSION = "1.0"
A2A_VERSION_HEADER = "A2A-Version"


def _actor_user_id() -> str:
    return require_context().user.user_id


def _actor_company_id() -> str:
    return require_active_company().company_id


def _a2a_channel(
    di: Di,
    flow_id: str,
    *,
    context: Context | None,
    flow_config: FlowConfig,
) -> A2AChannel:
    return get_channel(
        "a2a",
        flow_id,
        context=context,
        flow_config=flow_config,
        variables_service=di.variables_service,
        authz_service=di.authz_service,
        workflow_runtime=di.workflow_runtime,
        redis_client=di.redis_client,
        handoff_orchestrator_service=di.handoff_orchestrator_service,
        flow_factory=di.flow_factory,
        tool_registry=di.tool_registry,
        projection_service=di.a2a_task_projection_service,
        shared_storage=di.shared_storage,
        channel_registry=di.channel_registry,
        mail_service=di.mail_service,
        flow_ui_share_service=di.flow_ui_share_service,
        hitl_conversation_service=di.hitl_conversation_service,
        files_service=di.files_service,
    )


async def _require_view_flow(di: Di, flow_id: str) -> None:
    """View-право на flow; отсутствующий public-bundle сначала лениво материализуется,
    чтобы Check шёл по реальным FGA-туплам (403 — только про права, не про «ещё не досеяно»)."""
    if await FlowConfig.current_for_flow(flow_id) is None:
        _ = await _materialize_public_bundle(di, flow_id)
    await di.authz_service.require_can_view(
        AuthzObject.flow(flow_id, company_id=_actor_company_id()), user_id=_actor_user_id()
    )


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
        "flow_ui_share_permission": {"viewer", "editor"},
        "flow_ui_share_flow_id": None,
        "flow_ui_share_branch_id": None,
        "flow_ui_share_context_id": None,
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
    request_origin = request.headers.get("origin", "").strip() or build_service_base_url(
        request
    ).rstrip("/")
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
            params_dict["metadata"] = {"branch": token_data.metadata["flow_ui_share_branch_id"]}
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
    di: Di,
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
        count_raw: JsonValue = await di.redis_client.eval(
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
    except TypeError, ValueError:
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
    if isinstance(allowed_origin, str) and allowed_origin.strip():
        # Браузер не шлёт Origin на same-origin GET: тогда origin запроса — сам сервис.
        request_origin = request.headers.get("origin", "").strip() or build_service_base_url(
            request
        ).rstrip("/")
        if request_origin != allowed_origin.strip():
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
    if (
        method in _EMBED_MESSAGE_METHODS
        and isinstance(allowed_branch_id, str)
        and allowed_branch_id.strip()
    ):
        effective_branch_id = allowed_branch_id.strip()
        metadata_dict = params_dict.get("metadata")
        if metadata_dict is None:
            params_dict["metadata"] = {"branch": effective_branch_id}
        elif isinstance(metadata_dict, dict):
            request_branch = _metadata_effective_branch(metadata_dict)
            if request_branch is None:
                metadata_dict["branch"] = effective_branch_id
            elif request_branch != effective_branch_id:
                return {
                    "code": -32000,
                    "message": "Embed session token is not allowed for this branch",
                }
        else:
            return {"code": -32602, "message": "Invalid params: metadata must be object"}

    logger.info(
        "flows.embed_session_validated",
        flow_id=flow_id,
        branch_id=_embed_session_branch_from_token_metadata(metadata) or "default",
        company_id=token_data.company_id,
        origin=request.headers.get("origin", ""),
        issuer=metadata.get("issued_by", "unknown"),
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
    flow_id: str,
    version: str | None = None,
    di: Di | None = None,
) -> FlowConfig | None:
    """
    Получает конфигурацию агента.

    Аргументы:
        flow_id: ID агента
        version: Версия агента (опционально). Если не указана - возвращает latest.
        di: DI для ленивой материализации public-bundle при промахе.
    """
    if version:
        return await FlowConfig.by_flow_id_and_version(flow_id, version)
    config = await FlowConfig.current_for_flow(flow_id)
    if config is None and di is not None:
        return await _materialize_public_bundle(di, flow_id)
    return config


async def _materialize_public_bundle(di: Di, flow_id: str) -> FlowConfig | None:
    """Загрузить public-bundle из registry в активную компанию при первом обращении.

    Публичные bundle копируются компаниям в company_init; агент, добавленный
    позже, доезжает до уже существующих компаний здесь — по первому запросу
    к его flow_id. Возвращает None, если flow_id не является public-bundle
    (дальше обычный 404).
    """
    flows_src_dir = Path(__file__).resolve().parents[2]
    registry_path = flows_src_dir / "registry.yaml"
    if not registry_path.exists():
        return None
    loaded = parse_yaml_value(registry_path.read_text(encoding="utf-8"), "registry.yaml")
    registry = FlowBundleRegistry.model_validate(
        require_json_object(loaded, "registry.yaml") if loaded is not None else {}
    )
    entry = next((item for item in registry.flows if item.id == flow_id), None)
    if entry is None or not entry.public:
        return None
    loader = FlowsLoader(
        bundles_dir=flows_src_dir / "bundles",
        registry_path=registry_path,
        flow_access_service=di.flow_access_service,
        files_service=di.files_service,
    )
    try:
        _ = await loader.reload_flow_bundle(flow_id)
    except ValueError:
        return None
    return await FlowConfig.current_for_flow(flow_id)


def _get_base_url(request: Request) -> str:
    return build_service_base_url(request, include_default_port=True)


@router.get("/{flow_id}/.well-known/agent-card.json")
async def get_agent_card_well_known(
    flow_id: str,
    request: Request,
    di: Di,
    v: str | None = None,
) -> JsonObject:
    """
    Agent Card по well-known URL.

    Параметры query:
        v: версия агента (опционально)
    """
    await _require_view_flow(di, flow_id)
    config = await _get_flow_config(flow_id, version=v, di=di)
    if not config:
        raise WsCommandError("not_found", f"Flow '{flow_id}' not found", error_code="not_found")

    context = get_context()
    channel = _a2a_channel(di, flow_id, context=context, flow_config=config)
    base_url = _get_base_url(request)
    try:
        return await channel.get_agent_card(base_url)
    except ValueError as e:
        raise_not_found(e)


@router.get("/{flow_id}")
async def get_agent_card(
    flow_id: str,
    request: Request,
    di: Di,
    v: str | None = None,
) -> JsonObject:
    """
    Agent Card по A2A спецификации - GET на URL агента.

    Параметры query:
        v: версия агента (опционально)
    """
    await _require_view_flow(di, flow_id)
    config = await _get_flow_config(flow_id, version=v, di=di)
    if not config:
        raise WsCommandError("not_found", f"Flow '{flow_id}' not found", error_code="not_found")

    context = get_context()
    channel = _a2a_channel(di, flow_id, context=context, flow_config=config)
    base_url = _get_base_url(request)
    try:
        return await channel.get_agent_card(base_url)
    except ValueError as e:
        raise_not_found(e)


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
) -> AsyncGenerator[str, None]:
    async for event in handler.on_subscribe_to_task(params):
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
    di: Di,
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
            di=di,
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

    if embed_target is None and not _is_flow_ui_share_token(token_data):
        await _require_view_flow(di, flow_id)
    config = await _get_flow_config(flow_id, version=version, di=di)
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

    handler = _a2a_channel(di, flow_id, context=context, flow_config=config)

    # Группы пользователя для проверки прав доступа
    # 1. Из metadata (для тестов и внутренних вызовов)
    # 2. Из request.state.user (из JWT через middleware)
    user_groups_raw = metadata.get("__user_groups__")
    if user_groups_raw is None:
        user_groups = _get_user_groups(request)
    elif isinstance(user_groups_raw, list) and all(
        isinstance(item, str) for item in user_groups_raw
    ):
        user_groups = user_groups_raw
    else:
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {
                "code": -32602,
                "message": "Invalid params: metadata.__user_groups__ must be string array",
            },
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
            return {"jsonrpc": "2.0", "id": rpc_id, "result": rpc_result_to_json_dict(result)}

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
            return {"jsonrpc": "2.0", "id": rpc_id, "result": rpc_result_to_json_dict(result)}

        if method == LIST_TASKS:
            params = _parse_proto_params(params_dict, ListTasksRequest)
            result = await handler.on_list_tasks(params, context=channel_context)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": rpc_result_to_json_dict(result)}

        if method == CANCEL_TASK:
            params = _parse_proto_params(params_dict, CancelTaskRequest)
            result = await handler.on_cancel_task(params)
            if result is None:
                return {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": _a2a_rpc_error(A2AErrorCode.TASK_NOT_FOUND),
                }
            return {"jsonrpc": "2.0", "id": rpc_id, "result": rpc_result_to_json_dict(result)}

        if method == SUBSCRIBE_TO_TASK:
            params = _parse_proto_params(params_dict, SubscribeToTaskRequest)
            return StreamingResponse(
                _handle_subscribe_streaming(handler, params, rpc_id),
                media_type="text/event-stream",
                headers=_SSE_HEADERS,
            )

        if method == GET_TASK_PUSH_NOTIFICATION_CONFIG:
            params = _parse_proto_params(params_dict, GetTaskPushNotificationConfigRequest)
            result = await handler.on_get_task_push_notification_config(params)
            if result is None:
                return {"jsonrpc": "2.0", "id": rpc_id, "result": None}
            return {"jsonrpc": "2.0", "id": rpc_id, "result": rpc_result_to_json_dict(result)}

        if method == CREATE_TASK_PUSH_NOTIFICATION_CONFIG:
            params = _parse_proto_params(params_dict, TaskPushNotificationConfig)
            result = await handler.on_create_task_push_notification_config(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": rpc_result_to_json_dict(result)}

        if method == DELETE_TASK_PUSH_NOTIFICATION_CONFIG:
            params = _parse_proto_params(params_dict, DeleteTaskPushNotificationConfigRequest)
            await handler.on_delete_task_push_notification_config(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": None}

        if method == LIST_TASK_PUSH_NOTIFICATION_CONFIGS:
            params = _parse_proto_params(params_dict, ListTaskPushNotificationConfigsRequest)
            result = await handler.on_list_task_push_notification_configs(params)
            return {"jsonrpc": "2.0", "id": rpc_id, "result": rpc_result_to_json_dict(result)}

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
        logger.warning("flows.a2a.invalid_params", method=method, error=str(e))
        err = {"code": -32602, "message": str(e)}
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, -32602, str(e))
        return {"jsonrpc": "2.0", "id": rpc_id, "error": err}
    except A2AApplicationError as e:
        logger.warning("flows.a2a.application_error", method=method, error=str(e))
        err = e.to_json_rpc_error()
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, int(e.code), e.message)
        return {"jsonrpc": "2.0", "id": rpc_id, "error": err}
    except PermissionDenied as e:
        logger.warning("flows.a2a.permission_denied", method=method, error=str(e))
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
        logger.exception("flows.a2a.method_failed", method=method, error=str(e))
        if method in _STREAM_METHODS:
            return _sse_error_response(rpc_id, -32000, str(e))
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(e)}}


@router.post("/{flow_id}")
async def json_rpc_handler(
    flow_id: str,
    request: Request,
    di: Di,
    v: str | None = None,
):
    return await _json_rpc_handler_internal(
        flow_id=flow_id,
        request=request,
        di=di,
        v=v,
    )


@router.post("/embed/{embed_id}")
async def json_rpc_embed_handler(
    embed_id: str,
    request: Request,
    di: Di,
    v: str | None = None,
):
    embed_target = await resolve_embed_target(embed_id)
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
        di=di,
        v=v,
        embed_target=embed_target,
    )


async def _flow_interface_internal(
    *,
    flow_id: str,
    branch_id: str,
    request: Request,
    di: Di,
    embed_target: EmbedTarget | None = None,
) -> FlowInterfaceResponse:
    token_data_raw = _request_state_mapping(request).get("token_data")
    token_data = token_data_raw if isinstance(token_data_raw, TokenData) else None
    is_embed_session = _is_embed_session_token(token_data)
    is_share_session = _is_flow_ui_share_token(token_data)
    if embed_target is None and not is_share_session and not is_embed_session:
        await _require_view_flow(di, flow_id)
    config = await _get_flow_config(flow_id, di=di)
    if config is None:
        raise WsCommandError("not_found", f"Flow '{flow_id}' not found", error_code="not_found")
    if embed_target is None and config.branches and branch_id != "default":
        if branch_id not in config.branches:
            raise WsCommandError(
                "not_found", f"Branch '{branch_id}' not found", error_code="not_found"
            )
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
            raise WsCommandError("forbidden", claims_error, error_code="forbidden")

    share_permission: str | None = None
    if is_share_session and isinstance(token_data, TokenData):
        claims_error = _validate_flow_ui_share_claims(
            request=request,
            token_data=token_data,
            flow_id=flow_id,
            branch_id=branch_id,
        )
        if claims_error is not None:
            raise WsCommandError("forbidden", claims_error, error_code="forbidden")
        try:
            grant = await di.flow_ui_share_service.authorize(
                grant_id=str(token_data.metadata["flow_ui_share_grant_id"]),
                company_id=token_data.company_id,
                flow_id=flow_id,
                context_id=str(token_data.metadata["flow_ui_share_context_id"]),
                require_editor=False,
            )
        except PermissionError as exc:
            raise_forbidden(exc)
        share_permission = grant.permission

    document = config.interface_for_branch(branch_id)
    if embed_target is not None:
        document = document.with_embed_overrides(
            conversation=embed_target.conversation,
            start_page_id=embed_target.start_page_id,
        )
    settings = document.conversation_settings()
    look = embed_target.look if embed_target is not None else None
    return FlowInterfaceResponse(
        flow_id=flow_id,
        branch_id=branch_id,
        document=document,
        viewer=FlowInterfaceViewer(
            can_edit_flow=not is_embed_session and not is_share_session,
            can_interact=share_permission != "viewer",
            can_share=(
                not is_share_session
                and (not is_embed_session or (look is not None and look.session_share_enabled))
            ),
            auth_mode=(
                "share" if is_share_session else "embed" if is_embed_session else "platform"
            ),
        ),
        look=look,
        capabilities=FlowInterfaceCapabilities(
            cancel=settings.allow_cancel and share_permission != "viewer",
            files=settings.show_files_panel and not is_share_session,
            voice=(
                settings.allow_voice
                and share_permission != "viewer"
                and (look is None or look.voice_enabled)
            ),
        ),
        flow_identity=FlowInterfaceIdentity(
            title=config.name,
            image_url=document.agent_identity_image_url(),
        ),
    )


@router.get("/{flow_id}/interface", response_model=FlowInterfaceResponse)
async def get_flow_interface(
    flow_id: str,
    request: Request,
    di: Di,
    branch_id: str = "default",
) -> FlowInterfaceResponse:
    """Документ интерфейса и права для авторизованной поверхности платформы."""
    return await _flow_interface_internal(
        flow_id=flow_id,
        branch_id=branch_id,
        request=request,
        di=di,
    )


@router.get("/embed/{embed_id}/interface", response_model=FlowInterfaceResponse)
async def get_embed_interface(
    embed_id: str,
    request: Request,
    di: Di,
) -> FlowInterfaceResponse:
    """Документ интерфейса embed-поверхности с настройками EmbedConfig."""
    embed_target = await resolve_embed_target(embed_id)
    if embed_target is None:
        raise WsCommandError("not_found", f"Embed not found: {embed_id}", error_code="not_found")
    if not embed_target.active:
        raise WsCommandError("forbidden", f"Embed disabled: {embed_id}", error_code="forbidden")
    return await _flow_interface_internal(
        flow_id=embed_target.flow_id,
        branch_id=embed_target.branch_id,
        request=request,
        di=di,
        embed_target=embed_target,
    )
