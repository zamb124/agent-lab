"""
WebSocket A2A endpoints.

Поддерживает те же JSON-RPC методы, что и HTTP A2A API,
но поверх WebSocket соединения.
"""

import json

from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    MessageSendParams,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.flows.config import get_settings
from apps.flows.src.channels import PermissionDenied
from apps.flows.src.channels.websocket import WebSocketChannel
from apps.flows.src.container import FlowContainer
from apps.flows.src.container_contracts import as_flow_runtime_container
from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import FlowConfig
from core.auth.utils import get_token_info
from core.context import Context, User, set_context
from core.logging import get_logger
from core.types import JsonArray, JsonObject, JsonValue, parse_json_value, require_json_object

logger = get_logger(__name__)
JsonRpcId = str | int
JWT_ALGORITHM = "HS256"


router = APIRouter(tags=["websocket"])


WS_A2A_METHODS = {
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
    set_context(context)

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

            if method not in WS_A2A_METHODS:
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
            params_dict["metadata"] = metadata

            try:
                if method == "message/send":
                    params = MessageSendParams.model_validate(params_dict)
                    result = await handler.on_message_send(
                        params, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": require_json_object(
                                result.model_dump(by_alias=True, exclude_none=True),
                                "message.send.result",
                            ),
                        },
                    )

                elif method == "message/stream":
                    params = MessageSendParams.model_validate(params_dict)
                    async for event in handler.on_message_stream(
                        params, context=channel_context
                    ):
                        event_data = event.model_dump(
                            by_alias=True, exclude_none=True
                        )
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": require_json_object(event_data, "message.stream.event"),
                            },
                        )

                elif method == "tasks/get":
                    req = TaskQueryParams.model_validate(params_dict)
                    result = await handler.on_get_task(req, context=channel_context)
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": require_json_object(
                                result.model_dump(by_alias=True, exclude_none=True),
                                "tasks.get.result",
                            )
                            if result
                            else None,
                        },
                    )

                elif method == "tasks/cancel":
                    req = TaskIdParams.model_validate(params_dict)
                    result = await handler.on_cancel_task(req, context=channel_context)
                    if result is None:
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "error": {
                                    "code": -32000,
                                    "message": "Task not found",
                                },
                            },
                        )
                    else:
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": require_json_object(
                                    result.model_dump(by_alias=True, exclude_none=True),
                                    "tasks.cancel.result",
                                ),
                            },
                        )

                elif method == "tasks/resubscribe":
                    params = TaskIdParams.model_validate(params_dict)
                    async for event in handler.on_resubscribe_to_task(
                        params, context=channel_context
                    ):
                        event_data = event.model_dump(
                            by_alias=True, exclude_none=True
                        )
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": require_json_object(event_data, "tasks.resubscribe.event"),
                            },
                        )

                elif method == "tasks/pushNotificationConfig/get":
                    req = GetTaskPushNotificationConfigParams.model_validate(params_dict)
                    result = await handler.on_get_task_push_notification_config(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": require_json_object(
                                result.model_dump(by_alias=True, exclude_none=True),
                                "pushNotificationConfig.get.result",
                            )
                            if result
                            else None,
                        },
                    )

                elif method == "tasks/pushNotificationConfig/set":
                    params = TaskPushNotificationConfig.model_validate(params_dict)
                    result = await handler.on_set_task_push_notification_config(
                        params, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": require_json_object(
                                result.model_dump(by_alias=True, exclude_none=True),
                                "pushNotificationConfig.set.result",
                            ),
                        },
                    )

                elif method == "tasks/pushNotificationConfig/delete":
                    req = DeleteTaskPushNotificationConfigParams.model_validate(params_dict)
                    await handler.on_delete_task_push_notification_config(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {"jsonrpc": "2.0", "id": rpc_id, "result": None},
                    )

                elif method == "tasks/pushNotificationConfig/list":
                    req = ListTaskPushNotificationConfigParams.model_validate(params_dict)
                    result = await handler.on_list_task_push_notification_config(
                        req, context=channel_context
                    )
                    result_items: JsonArray = []
                    for item in result:
                        result_items.append(
                            require_json_object(
                                item.model_dump(by_alias=True, exclude_none=True),
                                "pushNotificationConfig.list.result[]",
                            )
                        )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": result_items,
                        },
                    )

                elif method == "agent/getAuthenticatedExtendedCard":
                    card = await handler.on_get_authenticated_extended_card(
                        params_dict, context=channel_context
                    )
                    if card:
                        result_data = require_json_object(
                            card.model_dump(by_alias=True, exclude_none=True),
                            "agent.authenticated_card",
                        )
                    else:
                        base_url = ""
                        result_data = require_json_object(
                            await handler.get_agent_card(base_url),
                            "agent.card",
                        )
                    await _send_json(
                        websocket,
                        {"jsonrpc": "2.0", "id": rpc_id, "result": result_data},
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
