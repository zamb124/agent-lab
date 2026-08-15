"""Helpers for durable Flow UI session/share tests against real container + DB."""

from __future__ import annotations

import uuid
from typing import Any

from a2a.types import Message, Role
from google.protobuf.json_format import MessageToDict
from httpx import AsyncClient

from apps.flows.src.a2a.interaction_parser import parse_flow_ui_command
from apps.flows.src.container import get_container
from apps.flows.src.models.flow_config import Edge, FlowConfig
from apps.flows.src.services.flow_ui_session_service import (
    FlowUISessionCommandResult,
    FlowUISessionService,
)
from core.a2a import (
    A2A_EXTENSIONS_HEADER,
    A2UI_EXTENSION_URI,
    A2UI_MIME_TYPE,
    A2UI_PLATFORM_CATALOG_ID,
    PLATFORM_UI_BOOTSTRAP_ACTION,
    PLATFORM_UI_SUBMIT_ACTION,
    PLATFORM_UI_SYNC_ACTION,
    A2ARepresentation,
    A2ARepresentationSnapshot,
    struct_from_mapping,
)
from core.a2ui import A2UI091Codec
from core.context import require_context
from core.models.flow_interface import default_flow_interface_config
from core.models.flow_ui_share import FlowUIShareGrant
from core.state import ExecutionState
from core.state.flow_ui import FlowUIDocument
from core.types import JsonObject
from tests.flows._a2a_v1 import A2A_HEADERS, SEND_MESSAGE, a2a_rpc


def flow_ui_a2a_headers(base: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(base or {})
    merged.update(A2A_HEADERS)
    merged[A2A_EXTENSIONS_HEADER] = A2UI_EXTENSION_URI
    return merged


def flow_ui_representation() -> A2ARepresentationSnapshot:
    return A2ARepresentationSnapshot(
        representation=A2ARepresentation.A2UI_0_9_1,
        negotiated_extensions=[A2UI_EXTENSION_URI],
        extension_uri=A2UI_EXTENSION_URI,
        catalog_id=A2UI_PLATFORM_CATALOG_ID,
        output_mime_type=A2UI_MIME_TYPE,
    )


def flow_ui_command_message(
    *,
    action: str,
    context_id: str,
    action_id: str,
    revision: int | None = None,
    message_value: str | None = None,
    values: JsonObject | None = None,
    surfaces_values: dict[str, JsonObject] | None = None,
    session_view_state: JsonObject | None = None,
    active_page_id: str = "main",
) -> Message:
    source_component_id = "submit" if action == PLATFORM_UI_SUBMIT_ACTION else "root"
    part = A2UI091Codec().encode_data_part(
        [
            {
                "version": "v0.9.1",
                "action": {
                    "name": action,
                    "surfaceId": "main",
                    "sourceComponentId": source_component_id,
                    "timestamp": "2026-08-04T12:00:00Z",
                    "context": (
                        {"formId": "message-form"}
                        if action == PLATFORM_UI_SUBMIT_ACTION
                        else {}
                    ),
                },
            }
        ]
    )
    platform_ui: JsonObject = {"actionId": action_id}
    if revision is not None:
        view_state: JsonObject = (
            dict(session_view_state)
            if session_view_state is not None
            else {"activeTabs": {"main": "conversation"}}
        )
        platform_ui.update(
            {
                "documentId": f"flow-ui:{context_id}",
                "revision": revision,
                "clientMutationId": action_id,
                "activePageId": active_page_id,
                "sessionViewState": view_state,
            }
        )
    metadata: JsonObject = {
        "a2uiClientCapabilities": {
            "v0.9.1": {
                "supportedCatalogIds": [A2UI_PLATFORM_CATALOG_ID],
                "inlineCatalogs": [],
            }
        },
        "platformUi": platform_ui,
    }
    if surfaces_values is not None:
        if values is not None or message_value is not None:
            raise ValueError("surfaces_values cannot be combined with values/message_value")
        client_surfaces = {
            surface_id: {"values": dict(surface_values)}
            for surface_id, surface_values in surfaces_values.items()
        }
    else:
        surface_values: JsonObject
        if values is not None:
            surface_values = dict(values)
        elif message_value is not None:
            surface_values = {"message": message_value, "files": []}
        else:
            surface_values = {"message": "", "files": []}
        client_surfaces = {
            "main": {
                "content": {"forged": "ignored"},
                "values": surface_values,
                "system": {"forged": "ignored"},
            }
        }
    if (
        surfaces_values is not None
        or message_value is not None
        or values is not None
        or action
        in {
            PLATFORM_UI_SYNC_ACTION,
            PLATFORM_UI_SUBMIT_ACTION,
        }
    ):
        metadata["a2uiClientDataModel"] = {
            "version": "v0.9.1",
            "surfaces": client_surfaces,
        }
    return Message(
        message_id=f"message-{action_id}",
        context_id=context_id,
        role=Role.ROLE_USER,
        parts=[part],
        extensions=[A2UI_EXTENSION_URI],
        metadata=struct_from_mapping(metadata),
    )


def flow_ui_protojson_message(
    *,
    action: str,
    context_id: str,
    action_id: str,
    revision: int | None = None,
    message_value: str | None = None,
    values: JsonObject | None = None,
) -> dict[str, Any]:
    message = flow_ui_command_message(
        action=action,
        context_id=context_id,
        action_id=action_id,
        revision=revision,
        message_value=message_value,
        values=values,
    )
    wire: dict[str, Any] = {
        "messageId": message.message_id,
        "role": "ROLE_USER",
        "contextId": context_id,
        "extensions": [A2UI_EXTENSION_URI],
        "parts": [MessageToDict(part) for part in message.parts],
    }
    if message.HasField("metadata"):
        wire["metadata"] = MessageToDict(message.metadata)
    return wire


async def bootstrap_flow_ui_session(
    *,
    flow_id: str | None = None,
    context_id: str | None = None,
    branch_id: str = "default",
    user_id: str | None = None,
    initial_document: FlowUIDocument | None = None,
) -> tuple[str, str, str, FlowUISessionCommandResult]:
    context = require_context()
    owner_user_id = user_id if user_id is not None else context.user.user_id
    resolved_flow_id = flow_id if flow_id is not None else f"flow-ui-{uuid.uuid4().hex}"
    resolved_context_id = (
        context_id if context_id is not None else f"context-{uuid.uuid4().hex}"
    )
    session_id = f"{resolved_flow_id}:{resolved_context_id}"
    container = get_container()
    config = await container.flow_repository.get(resolved_flow_id)
    if config is None:
        config = FlowConfig(
            flow_id=resolved_flow_id,
            name=resolved_flow_id,
            entry="main",
            nodes={
                "main": {
                    "type": "code",
                    "code": "async def run(args, state): return state",
                }
            },
            edges=[Edge(from_node="main", to_node=None)],
        )
        _ = await container.flow_repository.set(config)
    if context.active_company is None:
        raise AssertionError("active company required for flow authz sync")
    await container.flow_access_service.sync_flow_saved(
        config,
        company_id=context.active_company.company_id,
        owner_user_id=owner_user_id,
    )
    service = FlowUISessionService(container.workflow_runtime)
    if initial_document is None:
        document = default_flow_interface_config().template.materialize(
            document_id=f"flow-ui:{resolved_context_id}"
        )
    else:
        document = initial_document.model_copy(deep=True)
        document.document_id = f"flow-ui:{resolved_context_id}"
        document.revision = 1
    command = parse_flow_ui_command(
        flow_ui_command_message(
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=resolved_context_id,
            action_id=f"bootstrap-{uuid.uuid4().hex}",
        )
    )
    if command is None:
        raise AssertionError("bootstrap command failed to parse")
    result = await service.bootstrap(
        command=command,
        task_id=f"task-bootstrap-{uuid.uuid4().hex}",
        context_id=resolved_context_id,
        session_id=session_id,
        user_id=owner_user_id,
        initiator_user_id=owner_user_id,
        branch_id=branch_id,
        initial_document=document,
        representation=flow_ui_representation(),
    )
    return resolved_flow_id, resolved_context_id, session_id, result


async def sync_flow_ui_session(
    *,
    flow_id: str,
    context_id: str,
    revision: int,
    message_value: str | None = None,
    action_id: str | None = None,
    values: JsonObject | None = None,
    surfaces_values: dict[str, JsonObject] | None = None,
    session_view_state: JsonObject | None = None,
    active_page_id: str = "main",
    user_id: str | None = None,
    share_grant: FlowUIShareGrant | None = None,
) -> FlowUISessionCommandResult:
    if surfaces_values is None and message_value is None and values is None:
        raise ValueError("sync_flow_ui_session requires message_value, values, or surfaces_values")
    context = require_context()
    actor_user_id = user_id if user_id is not None else context.user.user_id
    session_id = f"{flow_id}:{context_id}"
    service = FlowUISessionService(get_container().workflow_runtime)
    mutation_id = action_id if action_id is not None else f"sync-{uuid.uuid4().hex}"
    command = parse_flow_ui_command(
        flow_ui_command_message(
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id=mutation_id,
            revision=revision,
            message_value=message_value,
            values=values,
            surfaces_values=surfaces_values,
            session_view_state=session_view_state,
            active_page_id=active_page_id,
        )
    )
    if command is None:
        raise AssertionError("sync command failed to parse")
    return await service.sync(
        command=command,
        task_id=f"task-sync-{mutation_id}",
        context_id=context_id,
        session_id=session_id,
        user_id=actor_user_id,
        share_grant=share_grant,
    )


async def submit_flow_ui_session(
    *,
    flow_id: str,
    context_id: str,
    revision: int,
    message_value: str,
    action_id: str | None = None,
    user_id: str | None = None,
    share_grant: FlowUIShareGrant | None = None,
) -> FlowUISessionCommandResult:
    context = require_context()
    actor_user_id = user_id if user_id is not None else context.user.user_id
    session_id = f"{flow_id}:{context_id}"
    service = FlowUISessionService(get_container().workflow_runtime)
    mutation_id = action_id if action_id is not None else f"submit-{uuid.uuid4().hex}"
    command = parse_flow_ui_command(
        flow_ui_command_message(
            action=PLATFORM_UI_SUBMIT_ACTION,
            context_id=context_id,
            action_id=mutation_id,
            revision=revision,
            message_value=message_value,
        )
    )
    if command is None:
        raise AssertionError("submit command failed to parse")
    return await service.submit(
        command=command,
        task_id=f"task-submit-{mutation_id}",
        context_id=context_id,
        session_id=session_id,
        user_id=actor_user_id,
        representation=flow_ui_representation(),
        share_grant=share_grant,
    )


async def load_flow_ui_state(session_id: str) -> ExecutionState:
    state = await get_container().workflow_runtime.get_state(session_id)
    if state is None:
        raise AssertionError(f"Flow UI session missing: {session_id}")
    return state


async def a2a_flow_ui_send(
    client: AsyncClient,
    *,
    flow_id: str,
    action: str,
    context_id: str,
    action_id: str,
    revision: int | None = None,
    message_value: str | None = None,
    values: JsonObject | None = None,
    branch_id: str | None = None,
    auth_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "message": flow_ui_protojson_message(
            action=action,
            context_id=context_id,
            action_id=action_id,
            revision=revision,
            message_value=message_value,
            values=values,
        )
    }
    # The client sends the graph branch in params metadata next to variables.
    if branch_id is not None:
        params["metadata"] = {"branch": branch_id}
    payload = a2a_rpc(SEND_MESSAGE, params, rpc_id=action_id)
    response = await client.post(
        f"/flows/api/v1/{flow_id}",
        headers=flow_ui_a2a_headers(auth_headers),
        json=payload,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "error" not in body, body
    assert "result" in body, body
    result = body["result"]
    if not isinstance(result, dict):
        raise AssertionError(f"A2A Flow UI result must be object, got {type(result)}")
    return result


__all__ = [
    "a2a_flow_ui_send",
    "bootstrap_flow_ui_session",
    "flow_ui_a2a_headers",
    "flow_ui_command_message",
    "flow_ui_protojson_message",
    "flow_ui_representation",
    "load_flow_ui_state",
    "submit_flow_ui_session",
    "sync_flow_ui_session",
]
