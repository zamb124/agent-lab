from __future__ import annotations

import uuid

import pytest
from a2a.types import Message, Role

from apps.flows.src.a2a.interaction_parser import parse_flow_ui_command
from apps.flows.src.container import get_container
from apps.flows.src.services.flow_ui_session_service import (
    FlowUIDuplicateMutationError,
    FlowUISessionService,
)
from core.a2a import (
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
from core.state.flow_ui_delta import FlowUIRevisionConflictError
from core.types import JsonObject


def _representation() -> A2ARepresentationSnapshot:
    return A2ARepresentationSnapshot(
        representation=A2ARepresentation.A2UI_0_9_1,
        negotiated_extensions=[A2UI_EXTENSION_URI],
        extension_uri=A2UI_EXTENSION_URI,
        catalog_id=A2UI_PLATFORM_CATALOG_ID,
        output_mime_type=A2UI_MIME_TYPE,
    )


def _command_message(
    *,
    action: str,
    context_id: str,
    action_id: str,
    revision: int | None = None,
    message_value: str | None = None,
) -> Message:
    part = A2UI091Codec().encode_data_part(
        [
            {
                "version": "v0.9.1",
                "action": {
                    "name": action,
                    "surfaceId": "main",
                    "sourceComponentId": (
                        "submit" if action == PLATFORM_UI_SUBMIT_ACTION else "root"
                    ),
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
        platform_ui.update(
            {
                "documentId": f"flow-ui:{context_id}",
                "revision": revision,
                "clientMutationId": action_id,
                "activePageId": "main",
                "sessionViewState": {"activeTabs": {"main": "conversation"}},
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
    if message_value is not None:
        metadata["a2uiClientDataModel"] = {
            "version": "v0.9.1",
            "surfaces": {
                "main": {
                    "content": {"forged": "ignored"},
                    "values": {"message": message_value, "files": []},
                    "system": {"forged": "ignored"},
                }
            },
        }
    return Message(
        message_id=f"message-{action_id}",
        context_id=context_id,
        role=Role.ROLE_USER,
        parts=[part],
        extensions=[A2UI_EXTENSION_URI],
        metadata=struct_from_mapping(metadata),
    )


@pytest.mark.asyncio
async def test_bootstrap_sync_duplicate_occ_and_submit_are_one_durable_reducer(
    app: object,
) -> None:
    _ = app
    context = require_context()
    flow_id = f"flow-ui-{uuid.uuid4().hex}"
    context_id = f"context-{uuid.uuid4().hex}"
    session_id = f"{flow_id}:{context_id}"
    service = FlowUISessionService(get_container().workflow_runtime)
    initial_document = default_flow_interface_config().template.materialize(
        document_id=f"flow-ui:{context_id}"
    )

    bootstrap = parse_flow_ui_command(
        _command_message(
            action=PLATFORM_UI_BOOTSTRAP_ACTION,
            context_id=context_id,
            action_id="bootstrap-1",
        )
    )
    assert bootstrap is not None
    bootstrapped = await service.bootstrap(
        command=bootstrap,
        task_id="task-bootstrap",
        context_id=context_id,
        session_id=session_id,
        user_id=context.user.user_id,
        initiator_user_id=context.user.user_id,
        branch_id="default",
        initial_document=initial_document,
        representation=_representation(),
    )
    assert bootstrapped.state.ui_document.revision == 1
    assert bootstrapped.state.ui_document.document_id == f"flow-ui:{context_id}"

    sync = parse_flow_ui_command(
        _command_message(
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id="sync-1",
            revision=1,
            message_value="draft",
        )
    )
    assert sync is not None
    synced = await service.sync(
        command=sync,
        task_id="task-sync",
        context_id=context_id,
        session_id=session_id,
        user_id=context.user.user_id,
    )
    assert synced.was_applied
    assert synced.transition is not None
    assert synced.state.ui_document.revision == 2
    assert synced.state.ui_document.surfaces["main"].data_model.values == {
        "message": "draft",
        "files": [],
    }
    assert "forged" not in synced.state.ui_document.surfaces["main"].data_model.content
    assert synced.state.ui_document.session_view_state == {
        "activeTabs": {"main": "conversation"}
    }

    duplicate = await service.sync(
        command=sync,
        task_id="task-sync-retry",
        context_id=context_id,
        session_id=session_id,
        user_id=context.user.user_id,
    )
    assert not duplicate.was_applied
    assert duplicate.state.ui_document.revision == 2

    conflicting_reuse = parse_flow_ui_command(
        _command_message(
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id="sync-1",
            revision=1,
            message_value="different",
        )
    )
    assert conflicting_reuse is not None
    with pytest.raises(FlowUIDuplicateMutationError):
        _ = await service.sync(
            command=conflicting_reuse,
            task_id="task-sync-conflict",
            context_id=context_id,
            session_id=session_id,
            user_id=context.user.user_id,
        )

    stale = parse_flow_ui_command(
        _command_message(
            action=PLATFORM_UI_SYNC_ACTION,
            context_id=context_id,
            action_id="sync-stale",
            revision=1,
            message_value="stale",
        )
    )
    assert stale is not None
    with pytest.raises(FlowUIRevisionConflictError):
        _ = await service.sync(
            command=stale,
            task_id="task-sync-stale",
            context_id=context_id,
            session_id=session_id,
            user_id=context.user.user_id,
        )

    submit = parse_flow_ui_command(
        _command_message(
            action=PLATFORM_UI_SUBMIT_ACTION,
            context_id=context_id,
            action_id="submit-1",
            revision=2,
            message_value="run the flow",
        )
    )
    assert submit is not None
    submitted = await service.submit(
        command=submit,
        task_id="task-submit",
        context_id=context_id,
        session_id=session_id,
        user_id=context.user.user_id,
        representation=_representation(),
    )
    assert submitted.was_applied
    assert submitted.content == "run the flow"
    assert submitted.state.task_id == "task-submit"
    assert submitted.state.ui_document.revision == 3
    assert submitted.state.ui_interaction is not None
    assert submitted.state.ui_interaction.accepted_revision == 3
    assert submitted.state.ui_interaction.validated_values_snapshot == {
        "main": {"message": "run the flow", "files": []}
    }
    assert submitted.state.ui_document.surfaces["main"].data_model.values == {
        "message": "",
        "files": [],
    }

    reloaded = await get_container().workflow_runtime.get_state(session_id)
    assert reloaded is not None
    assert reloaded.ui_document == submitted.state.ui_document
    assert reloaded.ui_interaction == submitted.state.ui_interaction
