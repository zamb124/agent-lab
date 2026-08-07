"""Strict ingress parsing for Flow UI actions carried by ordinary A2A Messages."""

from __future__ import annotations

from enum import StrEnum

from a2a.types import Message, Part, Role
from pydantic import Field

from core.a2a import (
    A2UI_EXTENSION_URI,
    PLATFORM_UI_BOOTSTRAP_ACTION,
    PLATFORM_UI_SUBMIT_ACTION,
    PLATFORM_UI_SYNC_ACTION,
    is_a2ui_media_type,
    mapping_from_struct,
    message_to_json_dict,
)
from core.a2ui import DEFAULT_A2UI_CODEC_REGISTRY, A2UIDecodedInteraction
from core.models import StrictBaseModel
from core.types import JsonObject, require_json_object


class FlowUIIngressKind(StrEnum):
    BOOTSTRAP = "bootstrap"
    SYNC = "sync"
    SUBMIT = "submit"


_KIND_BY_ACTION: dict[str, FlowUIIngressKind] = {
    PLATFORM_UI_BOOTSTRAP_ACTION: FlowUIIngressKind.BOOTSTRAP,
    PLATFORM_UI_SYNC_ACTION: FlowUIIngressKind.SYNC,
    PLATFORM_UI_SUBMIT_ACTION: FlowUIIngressKind.SUBMIT,
}


class FlowUIInboundCommand(StrictBaseModel):
    """Validated wire command, before authorization and document-level checks."""

    kind: FlowUIIngressKind
    action_id: str = Field(min_length=1)
    client_mutation_id: str = Field(min_length=1)
    document_id: str | None = Field(default=None, min_length=1)
    base_revision: int | None = Field(default=None, ge=1)
    active_page_id: str | None = Field(default=None, min_length=1)
    session_view_state: JsonObject = Field(default_factory=dict)
    decoded: A2UIDecodedInteraction
    original_message: JsonObject


def _part_declares_a2ui(part: Part) -> bool:
    metadata = mapping_from_struct(part.metadata) if part.HasField("metadata") else {}
    declared = [part.media_type, metadata.get("mimeType")]
    return any(isinstance(value, str) and is_a2ui_media_type(value) for value in declared)


def _platform_ui_metadata(metadata: JsonObject) -> JsonObject:
    raw = metadata.get("platformUi")
    payload = require_json_object(raw, "message.metadata.platformUi")
    allowed = {
        "documentId",
        "revision",
        "actionId",
        "clientMutationId",
        "activePageId",
        "sessionViewState",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"message.metadata.platformUi contains unknown fields: {unknown!r}")
    return payload


def _optional_non_empty_string(payload: JsonObject, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"message.metadata.platformUi.{key} must be a non-empty string")
    return value.strip()


def _optional_revision(payload: JsonObject) -> int | None:
    value = payload.get("revision")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("message.metadata.platformUi.revision must be a positive integer")
    revision = int(value)
    if float(value) != float(revision) or revision < 1:
        raise ValueError("message.metadata.platformUi.revision must be a positive integer")
    return revision


def parse_flow_ui_command(message: Message) -> FlowUIInboundCommand | None:
    """Return a typed Flow UI command or ``None`` for an ordinary A2A Message."""
    candidates = [part for part in message.parts if _part_declares_a2ui(part)]
    if not candidates:
        return None
    if message.role != Role.ROLE_USER:
        raise ValueError("Flow UI commands must be sent by ROLE_USER")
    if A2UI_EXTENSION_URI not in message.extensions:
        raise ValueError("A2UI Message must declare the official extension URI")
    if len(candidates) != 1:
        raise ValueError("Flow UI command Message must contain exactly one A2UI data Part")

    metadata = mapping_from_struct(message.metadata) if message.HasField("metadata") else {}
    codec = DEFAULT_A2UI_CODEC_REGISTRY.get(A2UI_EXTENSION_URI)
    decoded = codec.decode_client_action(candidates[0], metadata)
    try:
        kind = _KIND_BY_ACTION[decoded.action.name]
    except KeyError as exc:
        raise ValueError(f"Unsupported Flow UI action: {decoded.action.name!r}") from exc

    platform_ui = _platform_ui_metadata(metadata)
    action_id = _optional_non_empty_string(platform_ui, "actionId")
    mutation_id = _optional_non_empty_string(platform_ui, "clientMutationId")
    if action_id is None:
        raise ValueError("message.metadata.platformUi.actionId is required")
    if mutation_id is None:
        mutation_id = action_id

    document_id = _optional_non_empty_string(platform_ui, "documentId")
    revision = _optional_revision(platform_ui)
    if kind is not FlowUIIngressKind.BOOTSTRAP:
        if document_id is None:
            raise ValueError("Flow UI sync/submit requires documentId")
        if revision is None:
            raise ValueError("Flow UI sync/submit requires revision")
        if decoded.data_model is None:
            raise ValueError("Flow UI sync/submit requires a2uiClientDataModel")

    active_page_id = _optional_non_empty_string(platform_ui, "activePageId")
    view_state_raw = platform_ui.get("sessionViewState", {})
    view_state = require_json_object(
        view_state_raw,
        "message.metadata.platformUi.sessionViewState",
    )
    return FlowUIInboundCommand(
        kind=kind,
        action_id=action_id,
        client_mutation_id=mutation_id,
        document_id=document_id,
        base_revision=revision,
        active_page_id=active_page_id,
        session_view_state=view_state,
        decoded=decoded,
        original_message=message_to_json_dict(message),
    )


__all__ = [
    "FlowUIInboundCommand",
    "FlowUIIngressKind",
    "parse_flow_ui_command",
]
