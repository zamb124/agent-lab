"""Helpers для тестов Flow UI поверх чистого A2A: ui-action сообщения, сессии, артефакты.

Upstream интерфейс отправляет либо ``text`` Part, либо ровно один ``data`` Part
``application/vnd.platform.ui-action+json``; downstream состояние читается из артефакта
``state`` (снимок + JSON Patch), рендеры — из артефакта ``ui``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from httpx2 import AsyncClient

from apps.flows.src.models.flow_config import Edge, FlowConfig
from apps.flows.src.state import ExecutionState
from core.clients.flow_ui_client import task_state, task_text, task_ui_events
from core.context import require_context
from core.types import JsonArray, JsonObject, JsonValue, parse_json_object, require_json_object
from core.ui_document.document import FlowUIDocument
from core.ui_document.protocol import FLOW_UI_ACTION_MEDIA_TYPE, FlowUIEvent, FlowUIRender
from tests.flows._a2a_v1 import A2A_HEADERS, GET_TASK, SEND_MESSAGE, a2a_rpc

ECHO_CODE = "async def run(args, state): return state"


def ui_action_message(
    *,
    context_id: str,
    action: str,
    source: str,
    fields: JsonObject | None = None,
    payload: JsonObject | None = None,
    message_id: str | None = None,
    task_id: str | None = None,
) -> JsonObject:
    """ProtoJSON Message с единственным ui-action data Part."""
    body: JsonObject = {
        "action": action,
        "source": source,
        "fields": dict(fields) if fields is not None else {},
        "payload": dict(payload) if payload is not None else {},
    }
    message: JsonObject = {
        "messageId": message_id if message_id is not None else f"message-{uuid.uuid4().hex}",
        "role": "ROLE_USER",
        "contextId": context_id,
        "parts": [{"data": body, "mediaType": FLOW_UI_ACTION_MEDIA_TYPE}],
    }
    if task_id is not None:
        message["taskId"] = task_id
    return message


def text_message(*, context_id: str, text: str, task_id: str | None = None) -> JsonObject:
    message: JsonObject = {
        "messageId": f"message-{uuid.uuid4().hex}",
        "role": "ROLE_USER",
        "contextId": context_id,
        "parts": [{"text": text}],
    }
    if task_id is not None:
        message["taskId"] = task_id
    return message


async def a2a_send(
    client: AsyncClient,
    *,
    flow_id: str,
    message: JsonObject,
    branch_id: str | None = None,
    auth_headers: dict[str, str] | None = None,
    rpc_id: str | None = None,
) -> JsonObject:
    """SendMessage к flow; возвращает ``result`` JSON-RPC ответа (Task)."""
    params: JsonObject = {"message": message}
    if branch_id is not None:
        params["metadata"] = {"branch": branch_id}
    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        headers={**(auth_headers or {}), **A2A_HEADERS},
        json=a2a_rpc(SEND_MESSAGE, params, rpc_id=rpc_id),
    )
    assert response.status_code == 200, response.text
    body = parse_json_object(response.content, "a2a response")
    assert "error" not in body, body
    return require_json_object(body["result"], "a2a result")


async def a2a_send_error(
    client: AsyncClient,
    *,
    flow_id: str,
    message: JsonObject,
    branch_id: str | None = None,
    auth_headers: dict[str, str] | None = None,
) -> JsonObject:
    """SendMessage, который обязан завершиться JSON-RPC ошибкой; возвращает объект ``error``."""
    params: JsonObject = {"message": message}
    if branch_id is not None:
        params["metadata"] = {"branch": branch_id}
    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        headers={**(auth_headers or {}), **A2A_HEADERS},
        json=a2a_rpc(SEND_MESSAGE, params),
    )
    body = parse_json_object(response.content, "a2a response")
    if response.status_code == 200:
        assert "error" in body, body
        return require_json_object(body["error"], "a2a error")
    return body


async def a2a_get_task(
    client: AsyncClient,
    *,
    flow_id: str,
    task_id: str,
    auth_headers: dict[str, str] | None = None,
) -> JsonObject:
    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        headers={**(auth_headers or {}), **A2A_HEADERS},
        json=a2a_rpc(GET_TASK, {"id": task_id}),
    )
    assert response.status_code == 200, response.text
    body = parse_json_object(response.content, "a2a response")
    assert "error" not in body, body
    return require_json_object(body["result"], "a2a task")


async def ensure_flow(
    *,
    flow_id: str | None = None,
    interface: FlowUIDocument | None = None,
    code: str = ECHO_CODE,
    owner_user_id: str | None = None,
    di,
) -> FlowConfig:
    """Code-flow из одной ноды с явным интерфейсом; authz синхронизируется как при сохранении."""
    context = require_context()
    resolved_flow_id = flow_id if flow_id is not None else f"flow-ui-{uuid.uuid4().hex}"
    config = await FlowConfig.current_for_flow(resolved_flow_id)
    if config is None:
        config = FlowConfig(
            flow_id=resolved_flow_id,
            name=resolved_flow_id,
            entry="main",
            nodes={"main": {"type": "code", "code": code}},
            edges=[Edge(from_node="main", to_node=None)],
        )
        if interface is not None:
            config.interface = interface
        _ = await FlowConfig.create_version(config)
    if context.active_company is None:
        raise AssertionError("active company required for flow authz sync")
    await di.flow_access_service.sync_flow_saved(
        config,
        company_id=context.active_company.company_id,
        owner_user_id=owner_user_id if owner_user_id is not None else context.user.user_id,
    )
    return config


async def load_flow_ui_state(session_id: str, di) -> ExecutionState:
    state = await di.workflow_runtime.get_state(session_id)
    if state is None:
        raise AssertionError(f"Flow UI session missing: {session_id}")
    return state


def state_from_task(task: JsonObject) -> JsonObject:
    """Итоговый ``state`` Task: снимок плюс накопленные JSON Patch (SDK ``task_state``)."""
    return task_state(task)


def ui_events_from_task(task: JsonObject) -> list[FlowUIEvent]:
    return task_ui_events(task)


def conversation_renders(events: Sequence[FlowUIEvent]) -> list[FlowUIRender]:
    return [event for event in events if isinstance(event, FlowUIRender)]


def text_of(task: JsonObject, name: str) -> str:
    return task_text(task, name)


def _parts(di: JsonObject) -> list[JsonObject]:
    parts = di.get("parts")
    if not isinstance(parts, list):
        raise AssertionError("parts must be a list")
    return [require_json_object(part, "parts[]") for part in parts]


def status_text(task: JsonObject) -> str:
    """Текст status.message завершённого Task: итог хода без LLM-потока (code flow)."""
    status = require_json_object(task.get("status"), "task.status")
    message = require_json_object(status.get("message"), "task.status.message")
    chunks: list[str] = []
    for part in _parts(message):
        text = part.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return "".join(chunks)


def json_array(value: JsonValue, label: str) -> JsonArray:
    if not isinstance(value, list):
        raise AssertionError(f"{label} must be a list, got {type(value)}")
    return value


__all__ = [
    "ECHO_CODE",
    "a2a_get_task",
    "a2a_send",
    "a2a_send_error",
    "conversation_renders",
    "ensure_flow",
    "json_array",
    "load_flow_ui_state",
    "state_from_task",
    "status_text",
    "text_message",
    "text_of",
    "ui_action_message",
    "ui_events_from_task",
]
