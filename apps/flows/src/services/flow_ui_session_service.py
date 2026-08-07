"""Authoritative Flow UI bootstrap, autosync and atomic submit commands."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from apps.flows.src.a2a.interaction_parser import (
    FlowUIInboundCommand,
    FlowUIIngressKind,
)
from apps.flows.src.durable_execution import (
    A2ATaskOpenedPayload,
    DurableWorkflowRuntime,
    UIDocumentPatchedPayload,
    UIInteractionAcceptedPayload,
    WorkflowConcurrencyError,
    WorkflowEventType,
    WorkflowStatus,
    begin_interaction_turn,
    create_initial_state,
)
from apps.flows.src.files.state_file_refs import upsert_state_file
from core.a2a import A2ARepresentationSnapshot
from core.models.flow_ui_share import FlowUIShareGrant
from core.state import ExecutionState
from core.state.flow_ui import (
    FlowUICommand,
    FlowUIDocument,
    FlowUIInteraction,
    FlowUINavigateCommand,
    FlowUISetDataCommand,
    FlowUITransition,
)
from core.state.flow_ui_contract import (
    FlowUISubmitContract,
    build_flow_ui_submit_contract,
    flow_ui_submit_file_refs,
)
from core.state.flow_ui_delta import (
    FlowUIRevisionConflictError,
    apply_flow_ui_commands,
)
from core.state.flow_ui_share_redaction import assert_share_mutation_allowed
from core.types import JsonObject, JsonValue, require_json_object

_ALLOWED_VIEW_STATE_KEYS = frozenset(
    {
        "activeTabs",
        "openSurfaces",
        "expandedComponents",
    }
)


class FlowUIDuplicateMutationError(ValueError):
    """The same idempotency key was reused for a different command."""


@dataclass(frozen=True)
class FlowUISessionCommandResult:
    state: ExecutionState
    transition: FlowUITransition | None
    was_applied: bool
    content: str


def _mutation_hash(command: FlowUIInboundCommand) -> str:
    payload = {
        "kind": str(command.kind),
        "document_id": command.document_id,
        "base_revision": command.base_revision,
        "action": command.decoded.action.model_dump(mode="json"),
        "data_model": (
            None
            if command.decoded.data_model is None
            else command.decoded.data_model.model_dump(mode="json")
        ),
        "active_page_id": command.active_page_id,
        "session_view_state": command.session_view_state,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _assert_session_access(
    state: ExecutionState,
    user_id: str,
    *,
    share_grant: FlowUIShareGrant | None,
    require_interact: bool,
) -> None:
    allowed = {state.user_id}
    if state.initiator_user_id is not None:
        allowed.add(state.initiator_user_id)
    if user_id in allowed:
        return
    if share_grant is None:
        raise PermissionError("Flow UI session is not owned by the current viewer")
    if (
        share_grant.flow_id != state.session_flow_id
        or share_grant.context_id != state.context_id
        or share_grant.document_id != state.ui_document.document_id
    ):
        raise PermissionError("Flow UI share grant does not match the durable session")
    if require_interact and share_grant.permission != "interact":
        raise PermissionError("Flow UI share grant is read-only")


def _pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _value_paths(value: JsonValue, *, path: str) -> list[str]:
    if isinstance(value, dict):
        if not value:
            # Empty object carries no client-owned leaves. Surfaces without
            # /values bindings (for example a freshly added page) sync with {}.
            return []
        paths: list[str] = []
        for key, child in value.items():
            paths.extend(
                _value_paths(
                    child,
                    path=f"{path}/{_pointer_segment(key)}",
                )
            )
        return paths
    if isinstance(value, list):
        return [path]
    return [path]


def _path_is_bound(path: str, binding_roots: set[str]) -> bool:
    return any(path == root or path.startswith(f"{root}/") for root in binding_roots)


def _validated_surface_values(
    document: FlowUIDocument,
    command: FlowUIInboundCommand,
) -> dict[str, JsonObject]:
    data_model = command.decoded.data_model
    if data_model is None:
        return {}
    values_by_surface: dict[str, JsonObject] = {}
    for surface_id, client_model in data_model.surfaces.items():
        surface = document.surfaces.get(surface_id)
        if surface is None:
            raise ValueError(f"Unknown Flow UI surface: {surface_id!r}")
        if not surface.send_data_model:
            raise ValueError(f"Flow UI surface does not accept client data: {surface_id!r}")
        unknown_namespaces = sorted(set(client_model) - {"content", "values", "system"})
        if unknown_namespaces:
            raise ValueError(
                f"Flow UI client data model contains unknown namespaces: {unknown_namespaces!r}"
            )
        raw_values = client_model.get("values", {})
        values = require_json_object(
            raw_values,
            f"a2uiClientDataModel.surfaces.{surface_id}.values",
        )
        binding_roots = {
            path
            for component in surface.components.values()
            for path in component.bindings.values()
            if path == "/values" or path.startswith("/values/")
        }
        for path in _value_paths(values, path="/values"):
            if not _path_is_bound(path, binding_roots):
                raise ValueError(f"Client value path is not bound by the surface: {path!r}")
        values_by_surface[surface_id] = values
    return values_by_surface


def _validate_view_state(command: FlowUIInboundCommand) -> None:
    unknown = sorted(set(command.session_view_state) - _ALLOWED_VIEW_STATE_KEYS)
    if unknown:
        raise ValueError(f"Flow UI session view state contains unknown fields: {unknown!r}")


def _validate_submit_source(document: FlowUIDocument, command: FlowUIInboundCommand) -> None:
    action = command.decoded.action
    surface = document.surfaces.get(action.surface_id)
    if surface is None:
        raise ValueError(f"Unknown Flow UI action surface: {action.surface_id!r}")
    component = surface.components.get(action.source_component_id)
    if component is None:
        raise ValueError(
            f"Unknown Flow UI action component: {action.source_component_id!r}"
        )
    if not any(candidate.name == action.name for candidate in component.actions.values()):
        raise ValueError("Flow UI action is not declared by the source component")


def _submit_contract(
    document: FlowUIDocument,
    values_by_surface: dict[str, JsonObject],
    command: FlowUIInboundCommand,
) -> FlowUISubmitContract:
    """Single projection of the submit into flow-visible content and values."""
    surface_id = command.decoded.action.surface_id
    return build_flow_ui_submit_contract(
        document,
        surface_id=surface_id,
        values=values_by_surface.get(surface_id, {}),
    )


def _cleared_composer_values(values: JsonObject) -> JsonObject:
    """Persist empty composer drafts after submit so stream snapshots cannot resurrect them."""
    cleared: JsonObject = dict(values)
    if "message" in cleared:
        cleared["message"] = ""
    if "files" in cleared:
        cleared["files"] = []
    return cleared


class FlowUISessionService:
    """Single reducer for all user-originated Flow UI state changes."""

    _workflow_runtime: DurableWorkflowRuntime

    def __init__(self, workflow_runtime: DurableWorkflowRuntime) -> None:
        self._workflow_runtime = workflow_runtime

    async def bootstrap(
        self,
        *,
        command: FlowUIInboundCommand,
        task_id: str,
        context_id: str,
        session_id: str,
        user_id: str,
        initiator_user_id: str | None,
        branch_id: str,
        initial_document: FlowUIDocument,
        representation: A2ARepresentationSnapshot,
        share_grant: FlowUIShareGrant | None = None,
    ) -> FlowUISessionCommandResult:
        if command.kind != FlowUIIngressKind.BOOTSTRAP:
            raise ValueError("bootstrap requires a platform.ui.bootstrap command")
        state = await self._workflow_runtime.get_state(session_id)
        created = False
        if state is None:
            if share_grant is not None:
                raise PermissionError("A share grant cannot create a new Flow UI session")
            state = create_initial_state(
                task_id=task_id,
                context_id=context_id,
                user_id=user_id,
                initiator_user_id=initiator_user_id,
                session_id=session_id,
                branch_id=branch_id,
                ui_document=initial_document,
            )
            state.a2a_representation = representation
            payload = A2ATaskOpenedPayload(
                task_id=task_id,
                context_id=context_id,
                document_id=state.ui_document.document_id,
                revision=state.ui_document.revision,
                action_id=command.action_id,
            )
            try:
                _ = await self._workflow_runtime.record_state_event(
                    session_id,
                    state,
                    event_type=WorkflowEventType.a2a_task_opened,
                    payload=payload,
                    snapshot=True,
                )
                created = True
            except WorkflowConcurrencyError:
                concurrent = await self._workflow_runtime.get_state(session_id)
                if concurrent is None:
                    raise
                state = concurrent
        _assert_session_access(
            state,
            user_id,
            share_grant=share_grant,
            require_interact=False,
        )
        if command.document_id is not None and command.document_id != state.ui_document.document_id:
            raise ValueError("Flow UI bootstrap document identity mismatch")
        return FlowUISessionCommandResult(
            state=state,
            transition=None,
            was_applied=created,
            content="",
        )

    async def sync(
        self,
        *,
        command: FlowUIInboundCommand,
        task_id: str,
        context_id: str,
        session_id: str,
        user_id: str,
        share_grant: FlowUIShareGrant | None = None,
    ) -> FlowUISessionCommandResult:
        if command.kind != FlowUIIngressKind.SYNC:
            raise ValueError("sync requires a platform.ui.sync command")
        return await self._apply_mutation(
            command=command,
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            user_id=user_id,
            representation=None,
            submit=False,
            share_grant=share_grant,
        )

    async def submit(
        self,
        *,
        command: FlowUIInboundCommand,
        task_id: str,
        context_id: str,
        session_id: str,
        user_id: str,
        representation: A2ARepresentationSnapshot,
        share_grant: FlowUIShareGrant | None = None,
    ) -> FlowUISessionCommandResult:
        if command.kind != FlowUIIngressKind.SUBMIT:
            raise ValueError("submit requires a platform.ui.submit command")
        return await self._apply_mutation(
            command=command,
            task_id=task_id,
            context_id=context_id,
            session_id=session_id,
            user_id=user_id,
            representation=representation,
            submit=True,
            share_grant=share_grant,
        )

    async def _apply_mutation(
        self,
        *,
        command: FlowUIInboundCommand,
        task_id: str,
        context_id: str,
        session_id: str,
        user_id: str,
        representation: A2ARepresentationSnapshot | None,
        submit: bool,
        share_grant: FlowUIShareGrant | None,
    ) -> FlowUISessionCommandResult:
        if command.document_id is None or command.base_revision is None:
            raise ValueError("Flow UI mutation requires document identity and revision")
        base_revision = command.base_revision
        mutation_hash = _mutation_hash(command)
        content_holder: list[str] = []

        def transform(state: ExecutionState) -> ExecutionState:
            _assert_session_access(
                state,
                user_id,
                share_grant=share_grant,
                require_interact=True,
            )
            if state.context_id != context_id:
                raise ValueError("Flow UI command context identity mismatch")
            if state.ui_document.document_id != command.document_id:
                raise ValueError("Flow UI command document identity mismatch")
            if state.ui_last_accepted_client_mutation_id == command.client_mutation_id:
                if state.ui_last_accepted_client_mutation_hash != mutation_hash:
                    raise FlowUIDuplicateMutationError(
                        "Flow UI clientMutationId was reused for different content"
                    )
                content_holder.append(state.content or "")
                return state

            _validate_view_state(command)
            values_by_surface = _validated_surface_values(state.ui_document, command)
            if share_grant is not None:
                assert_share_mutation_allowed(share_grant, values_by_surface)
            if submit:
                _validate_submit_source(state.ui_document, command)
            persist_values_by_surface = (
                {
                    surface_id: _cleared_composer_values(values)
                    for surface_id, values in values_by_surface.items()
                }
                if submit
                else values_by_surface
            )
            commands: list[FlowUICommand] = [
                FlowUISetDataCommand(
                    surface_id=surface_id,
                    path="/values",
                    value=values,
                )
                for surface_id, values in persist_values_by_surface.items()
            ]
            if command.active_page_id is not None:
                commands.append(FlowUINavigateCommand(page_id=command.active_page_id))
            try:
                result = apply_flow_ui_commands(
                    state.ui_document,
                    commands,
                    expected_revision=command.base_revision,
                    client_mutation_id=command.client_mutation_id,
                    allow_system_data=False,
                )
            except FlowUIRevisionConflictError:
                raise
            document = result.document
            if not result.changed:
                # A view-state-only mutation is still one accepted semantic
                # document revision.
                document = state.ui_document.model_copy(deep=True)
                document.revision += 1
                document.last_accepted_client_mutation_id = command.client_mutation_id
            if command.session_view_state:
                document.session_view_state = {
                    **document.session_view_state,
                    **command.session_view_state,
                }
            document = FlowUIDocument.model_validate(document.model_dump(mode="python"))
            state.ui_document = document
            state.ui_template_version = document.template_version
            state.ui_last_synced_at = datetime.now(timezone.utc)
            state.ui_last_accepted_client_mutation_id = command.client_mutation_id
            state.ui_last_accepted_client_mutation_hash = mutation_hash
            state.ui_conflict = None

            contract = _submit_contract(document, values_by_surface, command)
            content = contract.content
            content_holder.append(content)
            if submit:
                form_value = command.decoded.action.context.get("formId")
                if form_value is not None and not isinstance(form_value, str):
                    raise ValueError("Flow UI action context.formId must be a string")
                if representation is None:
                    raise ValueError("Flow UI submit requires negotiated representation")
                if state.terminal_task_state is not None:
                    state = begin_interaction_turn(
                        state,
                        task_id=task_id,
                        representation=representation,
                    )
                else:
                    state.task_id = task_id
                    state.terminal_task_state = None
                    state.terminal_task_error = None
                    state.a2a_representation = representation
                state.content = content
                # Flat, developer-facing channel: @state:ui_values.<field>.
                state.ui_values = dict(contract.values)
                # Tools (read_file) read ExecutionState.files — FileUpload lives in
                # a2ui values, not A2A Part.url. Upsert here (durable before worker)
                # so TaskIQ process_task never needs flow_ui_command to see attachments.
                for file_ref in flow_ui_submit_file_refs(contract):
                    upsert_state_file(state, file_ref)
                state.ui_interaction = FlowUIInteraction(
                    interaction_id=command.action_id,
                    action_id=command.action_id,
                    task_id=task_id,
                    context_id=context_id,
                    message_id=str(command.original_message["messageId"]),
                    document_id=document.document_id,
                    base_revision=base_revision,
                    accepted_revision=document.revision,
                    surface_id=command.decoded.action.surface_id,
                    source_component_id=command.decoded.action.source_component_id,
                    form_id=form_value,
                    page_id=document.active_page_id,
                    values_patch={
                        surface_id: {"values": values}
                        for surface_id, values in values_by_surface.items()
                    },
                    validated_values_snapshot={
                        surface_id: values
                        for surface_id, values in values_by_surface.items()
                    },
                    original_message=command.original_message,
                    submitted_at=command.decoded.action.timestamp,
                )
            return state

        if submit:
            event_type = WorkflowEventType.ui_interaction_accepted

            def payload_factory(
                before: ExecutionState,
                after: ExecutionState,
            ) -> UIInteractionAcceptedPayload:
                interaction = after.ui_interaction
                if interaction is None:
                    raise ValueError("Flow UI submit did not materialize an interaction")
                return UIInteractionAcceptedPayload(
                    task_id=task_id,
                    context_id=context_id,
                    document_id=after.ui_document.document_id,
                    base_revision=base_revision,
                    accepted_revision=after.ui_document.revision,
                    action_id=command.action_id,
                    interaction_id=interaction.interaction_id,
                    surface_id=interaction.surface_id,
                    source_component_id=interaction.source_component_id,
                    previous_task_id=(
                        before.task_id if before.task_id != after.task_id else None
                    ),
                    opened_new_task=before.terminal_task_state is not None,
                )

            before, after, append_result = (
                await self._workflow_runtime.update_state_atomic(
                    session_id,
                    event_type=event_type,
                    transform=transform,
                    payload_factory=payload_factory,
                    snapshot=False,
                    workflow_status=WorkflowStatus.running,
                )
            )
        else:
            event_type = WorkflowEventType.ui_document_patched

            def sync_payload_factory(
                _before: ExecutionState,
                after: ExecutionState,
            ) -> UIDocumentPatchedPayload:
                data_model = command.decoded.data_model
                return UIDocumentPatchedPayload(
                    task_id=task_id,
                    context_id=context_id,
                    document_id=after.ui_document.document_id,
                    base_revision=base_revision,
                    accepted_revision=after.ui_document.revision,
                    source="client:sync",
                    client_mutation_id=command.client_mutation_id,
                    surface_ids=(
                        [] if data_model is None else list(data_model.surfaces)
                    ),
                )

            before, after, append_result = (
                await self._workflow_runtime.update_state_atomic(
                    session_id,
                    event_type=event_type,
                    transform=transform,
                    payload_factory=sync_payload_factory,
                    snapshot=False,
                )
            )
        applied = append_result is not None
        transition = (
            FlowUITransition(
                transition_id=command.client_mutation_id,
                before=before.ui_document,
                after=after.ui_document,
                source="client:submit" if submit else "client:sync",
            )
            if applied and before.ui_document != after.ui_document
            else None
        )
        content = content_holder[-1] if content_holder else (after.content or "")
        return FlowUISessionCommandResult(
            state=after,
            transition=transition,
            was_applied=applied,
            content=content,
        )


__all__ = [
    "FlowUIDuplicateMutationError",
    "FlowUISessionCommandResult",
    "FlowUISessionService",
]
