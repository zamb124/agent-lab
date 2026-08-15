"""
WebSocket A2A endpoints.

Поддерживает те же JSON-RPC методы, что и HTTP A2A API,
но поверх WebSocket соединения.
"""

import json
from typing import TypeVar

from a2a.types import (
    CancelTaskRequest,
    DeleteTaskPushNotificationConfigRequest,
    GetTaskPushNotificationConfigRequest,
    GetTaskRequest,
    ListTaskPushNotificationConfigsRequest,
    ListTasksResponse,
    Message,
    SendMessageRequest,
    StreamResponse,
    SubscribeToTaskRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskPushNotificationConfig,
    TaskStatusUpdateEvent,
)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.message import DecodeError
from google.protobuf.message import Message as ProtoMessage

from apps.flows.config import get_settings
from apps.flows.src.channels import PermissionDenied
from apps.flows.src.channels.websocket import WebSocketChannel
from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import FlowConfig
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
    SEND_MESSAGE,
    SEND_STREAMING_MESSAGE,
    SUBSCRIBE_TO_TASK,
    A2AApplicationError,
    A2AErrorCode,
)
from core.auth.utils import get_token_info
from core.context import Context, User, set_context
from core.logging import get_logger
from core.types import JsonArray, JsonObject, JsonValue, parse_json_value, require_json_object

logger = get_logger(__name__)
JsonRpcId = str | int
JWT_ALGORITHM = "HS256"


router = APIRouter(tags=["websocket"])


def _proto_result(message: ProtoMessage) -> JsonObject:
    payload = require_json_object(MessageToDict(message), "a2a.ws.result")
    if isinstance(message, ListTasksResponse) and "nextPageToken" not in payload:
        payload["nextPageToken"] = ""
    return payload


def _stream_response_result(
    event: Message | Task | TaskStatusUpdateEvent | TaskArtifactUpdateEvent,
) -> JsonObject:
    if isinstance(event, TaskStatusUpdateEvent):
        stream = StreamResponse(status_update=event)
    elif isinstance(event, TaskArtifactUpdateEvent):
        stream = StreamResponse(artifact_update=event)
    elif isinstance(event, Task):
        stream = StreamResponse(task=event)
    else:
        stream = StreamResponse(message=event)
    return _proto_result(stream)


_TProto = TypeVar("_TProto", bound=ProtoMessage)


def _parse_proto_params(params_dict: JsonObject, proto_cls: type[_TProto]) -> _TProto:
    message = proto_cls()
    try:
        _ = ParseDict(dict(params_dict), message)
    except (DecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid params for {proto_cls.__name__}: {exc}") from exc
    return message


def _auth_jwt_secret() -> str:
    secret = get_settings().auth.jwt_secret_key
    if not secret:
        raise RuntimeError("auth.jwt_secret_key is required for WebSocket token auth")
    return secret


def _strict_json_rpc_id(raw_id: JsonValue | None) -> JsonRpcId | None:
    if raw_id is None:
        return None
    if isinstance(raw_id, bool):
        return None
    if isinstance(raw_id, (str, int)):
        return raw_id
    return None


def _string_list(raw: JsonValue | None) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


async def _get_flow_config(flow_id: str, container: FlowContainer) -> FlowConfig | None:
    return await container.flow_repository.get(flow_id)


def _get_user_groups_from_token(token: str | None) -> list[str]:
    if not token:
        return []
    info = get_token_info(
        token=token,
        jwt_secret=_auth_jwt_secret(),
        jwt_algorithm=JWT_ALGORITHM,
    )
    if not info:
        return []
    return _string_list(info.get("grps"))


def _extract_bearer_token(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization") or websocket.headers.get(
        "Authorization"
    )
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    token_query = websocket.query_params.get("token")
    if token_query:
        return token_query.strip()
    return None


async def _send_json(websocket: WebSocket, payload: JsonObject) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=False))


@router.websocket("/ws/{flow_id}")
async def websocket_a2a(flow_id: str, websocket: WebSocket, container: ContainerDep) -> None:
    config = await _get_flow_config(flow_id, container)
    if not config:
        await websocket.accept()
        await _send_json(
            websocket,
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": f"Flow not found: {flow_id}"},
            },
        )
        await websocket.close()
        return

    await websocket.accept()

    token = _extract_bearer_token(websocket)
    user_groups = _get_user_groups_from_token(token)
    user_groups_payload: JsonArray = []
    user_groups_payload.extend(user_groups)
    channel_context: JsonObject = {"user_groups": user_groups_payload}

    # Создаем Context для WebSocket (не проходит через HTTP middleware)
    user_id = "websocket_user"
    if token:
        token_info = get_token_info(
            token=token,
            jwt_secret=_auth_jwt_secret(),
            jwt_algorithm=JWT_ALGORITHM,
        )
        if token_info:
            token_user_id = token_info.get("id")
            if isinstance(token_user_id, (str, int)) and not isinstance(token_user_id, bool):
                user_id = str(token_user_id)

    context = Context(
        user=User(user_id=user_id, name="WebSocket User"),
        channel="websocket",
        flow_id=flow_id,
        metadata={"user_groups": user_groups_payload},
    )
    _ = set_context(context)

    handler = WebSocketChannel(
        flow_id,
        context=context,
        container=as_flow_runtime_container(container),
    )

    try:
        while True:
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                body_value = parse_json_value(raw_message, "websocket.request")
            except ValueError as e:
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {e}"},
                    },
                )
                continue

            if not isinstance(body_value, dict):
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32600,
                            "message": "Invalid Request: expected JSON object",
                        },
                    },
                )
                continue
            body = require_json_object(body_value, "websocket.request")

            rpc_id = _strict_json_rpc_id(body.get("id"))
            if rpc_id is None:
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32600,
                            "message": "Invalid Request: id must be string or integer",
                        },
                    },
                )
                continue

            method_raw = body.get("method")
            if not isinstance(method_raw, str) or not method_raw.strip():
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {
                            "code": -32600,
                            "message": "Invalid Request: missing 'method' field",
                        },
                    },
                )
                continue
            method = method_raw.strip()

            raw_params = body.get("params")
            if raw_params is None:
                params_dict: JsonObject = {}
            elif isinstance(raw_params, dict):
                params_dict = require_json_object(raw_params, "params")
            else:
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {"code": -32602, "message": "Invalid params: expected object"},
                    },
                )
                continue

            if method not in A2A_METHODS:
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}",
                        },
                    },
                )
                continue

            metadata_raw = params_dict.get("metadata")
            if metadata_raw is None:
                metadata: JsonObject = {}
            elif isinstance(metadata_raw, dict):
                metadata = require_json_object(metadata_raw, "params.metadata")
            else:
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {"code": -32602, "message": "Invalid params: metadata must be object"},
                    },
                )
                continue
            if metadata.get("__user_groups__") is None:
                metadata["__user_groups__"] = user_groups_payload
            # metadata только у SendMessage / SendStreamingMessage (protobuf schema)
            if method in (SEND_MESSAGE, SEND_STREAMING_MESSAGE):
                params_dict["metadata"] = metadata

            try:
                if method == SEND_MESSAGE:
                    params = _parse_proto_params(params_dict, SendMessageRequest)
                    result = await handler.on_message_send(params, context=channel_context)
                    await _send_json(
                        websocket,
                        {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)},
                    )

                elif method == SEND_STREAMING_MESSAGE:
                    params = _parse_proto_params(params_dict, SendMessageRequest)
                    async for event in handler.on_message_stream(
                        params, context=channel_context
                    ):
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": _stream_response_result(event),
                            },
                        )

                elif method == GET_TASK:
                    req = _parse_proto_params(params_dict, GetTaskRequest)
                    result = await handler.on_get_task(req, context=channel_context)
                    if result is None:
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "error": {
                                    "code": int(A2AErrorCode.TASK_NOT_FOUND),
                                    "message": A2A_ERROR_CODE_NAMES[A2AErrorCode.TASK_NOT_FOUND],
                                },
                            },
                        )
                    else:
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": _proto_result(result),
                            },
                        )

                elif method == CANCEL_TASK:
                    req = _parse_proto_params(params_dict, CancelTaskRequest)
                    result = await handler.on_cancel_task(req, context=channel_context)
                    if result is None:
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "error": {
                                    "code": int(A2AErrorCode.TASK_NOT_FOUND),
                                    "message": A2A_ERROR_CODE_NAMES[A2AErrorCode.TASK_NOT_FOUND],
                                },
                            },
                        )
                    else:
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": _proto_result(result),
                            },
                        )

                elif method == SUBSCRIBE_TO_TASK:
                    params = _parse_proto_params(params_dict, SubscribeToTaskRequest)
                    async for event in handler.on_subscribe_to_task(
                        params, context=channel_context
                    ):
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": _stream_response_result(event),
                            },
                        )

                elif method == GET_TASK_PUSH_NOTIFICATION_CONFIG:
                    req = _parse_proto_params(
                        params_dict, GetTaskPushNotificationConfigRequest
                    )
                    result = await handler.on_get_task_push_notification_config(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": _proto_result(result) if result is not None else None,
                        },
                    )

                elif method == CREATE_TASK_PUSH_NOTIFICATION_CONFIG:
                    params = _parse_proto_params(params_dict, TaskPushNotificationConfig)
                    result = await handler.on_create_task_push_notification_config(
                        params, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)},
                    )

                elif method == DELETE_TASK_PUSH_NOTIFICATION_CONFIG:
                    req = _parse_proto_params(
                        params_dict, DeleteTaskPushNotificationConfigRequest
                    )
                    await handler.on_delete_task_push_notification_config(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {"jsonrpc": "2.0", "id": rpc_id, "result": None},
                    )

                elif method == LIST_TASK_PUSH_NOTIFICATION_CONFIGS:
                    req = _parse_proto_params(
                        params_dict, ListTaskPushNotificationConfigsRequest
                    )
                    result = await handler.on_list_task_push_notification_configs(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {"jsonrpc": "2.0", "id": rpc_id, "result": _proto_result(result)},
                    )

                elif method == GET_EXTENDED_AGENT_CARD:
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "error": {
                                "code": int(A2AErrorCode.EXTENDED_AGENT_CARD_NOT_CONFIGURED),
                                "message": A2A_ERROR_CODE_NAMES[
                                    A2AErrorCode.EXTENDED_AGENT_CARD_NOT_CONFIGURED
                                ],
                            },
                        },
                    )

            except ValueError as e:
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {"code": -32602, "message": str(e)},
                    },
                )
            except A2AApplicationError as e:
                logger.warning(f"A2A application error for {method}: {e}")
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": e.to_json_rpc_error(),
                    },
                )
            except PermissionDenied as e:
                logger.warning(f"Permission denied for {method}: {e}")
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": e.error.to_json_rpc_error(),
                    },
                )
            except Exception as e:
                logger.exception(f"Error handling WebSocket method {method}: {e}")
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {"code": -32000, "message": str(e)},
                    },
                )
    finally:
        await websocket.close()
