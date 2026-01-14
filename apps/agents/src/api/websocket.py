"""
WebSocket A2A endpoints.

Поддерживает те же JSON-RPC методы, что и HTTP A2A API,
но поверх WebSocket соединения.
"""

import json
from typing import Any, Dict, Optional

from a2a.types import (
    DeleteTaskPushNotificationConfigParams,
    GetTaskPushNotificationConfigParams,
    ListTaskPushNotificationConfigParams,
    MessageSendParams,
    SendMessageRequest,
    SendStreamingMessageRequest,
    SetTaskPushNotificationConfigRequest,
    TaskIdParams,
    TaskPushNotificationConfig,
    TaskQueryParams,
    TaskResubscriptionRequest,
)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.auth.utils import get_token_info
from apps.agents.src.channels import PermissionDenied
from apps.agents.src.channels.websocket import WebSocketChannel
from apps.agents.config import get_settings
from apps.agents.src.container import get_container
from core.context import Context, User, set_context
from core.logging import get_logger
from apps.agents.src.models import AgentConfig

logger = get_logger(__name__)


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


async def _get_agent_config(agent_id: str) -> Optional[AgentConfig]:
    container = get_container()
    return await container.agent_repository.get(agent_id)


def _get_user_groups_from_token(token: str | None) -> list[str]:
    if not token:
        return []
    settings = get_settings()
    info = get_token_info(
        token=token,
        jwt_secret=settings.auth.jwt_secret,
        jwt_algorithm=settings.auth.jwt_algorithm,
    )
    if not info:
        return []
    groups = info.get("grps", [])
    return groups if isinstance(groups, list) else []


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


async def _send_json(websocket: WebSocket, payload: Dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=False))


@router.websocket("/ws/{agent_id}")
async def websocket_a2a(agent_id: str, websocket: WebSocket) -> None:
    config = await _get_agent_config(agent_id)
    if not config:
        await websocket.accept()
        await _send_json(
            websocket,
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32000, "message": f"Agent not found: {agent_id}"},
            },
        )
        await websocket.close()
        return

    await websocket.accept()

    token = _extract_bearer_token(websocket)
    user_groups = _get_user_groups_from_token(token)
    channel_context: dict[str, Any] = {"user_groups": user_groups}

    # Создаем Context для WebSocket (не проходит через HTTP middleware)
    user_id = "websocket_user"
    if token:
        token_info = get_token_info(
            token=token,
            jwt_secret=get_settings().auth.jwt_secret,
            jwt_algorithm=get_settings().auth.jwt_algorithm,
        )
        if token_info:
            user_id = str(token_info.get("id", user_id))
    
    context = Context(
        user=User(user_id=user_id, name="WebSocket User"),
        channel="websocket",
        agent_id=agent_id,
        metadata={"user_groups": user_groups},
    )
    set_context(context)

    handler = WebSocketChannel(agent_id, context=context)

    try:
        while True:
            try:
                raw_message = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                body = json.loads(raw_message)
            except json.JSONDecodeError as e:
                await _send_json(
                    websocket,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {e}"},
                    },
                )
                continue

            if not isinstance(body, dict):
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

            rpc_id = body.get("id")
            method = body.get("method")
            params_dict = body.get("params", {}) or {}

            if not method:
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

            metadata = params_dict.get("metadata") or {}
            if metadata.get("__user_groups__") is None:
                metadata["__user_groups__"] = user_groups
            params_dict["metadata"] = metadata

            try:
                if method == "message/send":
                    req = SendMessageRequest(
                        id=rpc_id,
                        method="message/send",
                        params=MessageSendParams(**params_dict),
                    )
                    result = await handler.on_message_send(
                        req.params, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": result.model_dump(
                                by_alias=True, exclude_none=True
                            ),
                        },
                    )

                elif method == "message/stream":
                    req = SendStreamingMessageRequest(
                        id=rpc_id,
                        method="message/stream",
                        params=MessageSendParams(**params_dict),
                    )
                    async for event in handler.on_message_stream(
                        req.params, context=channel_context
                    ):
                        event_data = event.model_dump(
                            by_alias=True, exclude_none=True
                        )
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": event_data,
                            },
                        )

                elif method == "tasks/get":
                    req = TaskQueryParams(**params_dict)
                    result = await handler.on_get_task(req, context=channel_context)
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": result.model_dump(
                                by_alias=True, exclude_none=True
                            )
                            if result
                            else None,
                        },
                    )

                elif method == "tasks/cancel":
                    req = TaskIdParams(**params_dict)
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
                                "result": result.model_dump(
                                    by_alias=True, exclude_none=True
                                ),
                            },
                        )

                elif method == "tasks/resubscribe":
                    req = TaskResubscriptionRequest(
                        id=rpc_id,
                        method="tasks/resubscribe",
                        params=TaskIdParams(**params_dict),
                    )
                    async for event in handler.on_resubscribe_to_task(
                        req.params, context=channel_context
                    ):
                        event_data = event.model_dump(
                            by_alias=True, exclude_none=True
                        )
                        await _send_json(
                            websocket,
                            {
                                "jsonrpc": "2.0",
                                "id": rpc_id,
                                "result": event_data,
                            },
                        )

                elif method == "tasks/pushNotificationConfig/get":
                    req = GetTaskPushNotificationConfigParams(**params_dict)
                    result = await handler.on_get_task_push_notification_config(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": result.model_dump(
                                by_alias=True, exclude_none=True
                            )
                            if result
                            else None,
                        },
                    )

                elif method == "tasks/pushNotificationConfig/set":
                    req = SetTaskPushNotificationConfigRequest(
                        id=rpc_id,
                        method="tasks/pushNotificationConfig/set",
                        params=TaskPushNotificationConfig(**params_dict),
                    )
                    result = await handler.on_set_task_push_notification_config(
                        req.params, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": result.model_dump(
                                by_alias=True, exclude_none=True
                            ),
                        },
                    )

                elif method == "tasks/pushNotificationConfig/delete":
                    req = DeleteTaskPushNotificationConfigParams(**params_dict)
                    await handler.on_delete_task_push_notification_config(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {"jsonrpc": "2.0", "id": rpc_id, "result": None},
                    )

                elif method == "tasks/pushNotificationConfig/list":
                    req = ListTaskPushNotificationConfigParams(**params_dict)
                    result = await handler.on_list_task_push_notification_config(
                        req, context=channel_context
                    )
                    await _send_json(
                        websocket,
                        {
                            "jsonrpc": "2.0",
                            "id": rpc_id,
                            "result": [
                                r.model_dump(by_alias=True, exclude_none=True)
                                for r in result
                            ],
                        },
                    )

                elif method == "agent/getAuthenticatedExtendedCard":
                    card = await handler.on_get_authenticated_extended_card(
                        params_dict, context=channel_context
                    )
                    if card:
                        result_data = card.model_dump(
                            by_alias=True, exclude_none=True
                        )
                    else:
                        base_url = ""
                        result_data = await handler.get_agent_card(base_url)
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


