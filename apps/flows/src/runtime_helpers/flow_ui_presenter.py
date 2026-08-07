"""Trusted projection of platform results into the materialized Flow UI document."""

from __future__ import annotations

import re
import uuid
from hashlib import sha256
from typing import Literal

from core.state import ExecutionState
from core.state.flow_ui import (
    FlowUIComponent,
    FlowUIPlacement,
    FlowUIResponsivePlacement,
    FlowUISetDataCommand,
    FlowUIUpsertComponentsCommand,
)
from core.state.flow_ui_effects import apply_trusted_ui_commands
from core.types import JsonObject

FlowUIArtifactKind = Literal[
    "file_collection",
    "skill_activity",
    "reflection_result",
    "action_preview",
    "action_result",
    "browser_preview",
    "activity",
]

_COMPONENT_TYPES: dict[FlowUIArtifactKind, str] = {
    "file_collection": "FileCollection",
    "skill_activity": "SkillActivity",
    "reflection_result": "ReflectionResult",
    "action_preview": "ActionPreview",
    "action_result": "ActionResult",
    "browser_preview": "BrowserPreview",
    "activity": "ActivityCard",
}


def _stable_token(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-")
    if normalized and len(normalized) <= 72:
        return normalized
    return sha256(value.encode("utf-8")).hexdigest()[:24]


def _pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _artifact_parent_id(state: ExecutionState, surface_id: str) -> str:
    surface = state.ui_document.surfaces[surface_id]
    for component in surface.components.values():
        if component.type == "ArtifactFeed" and component.kind == "container":
            return component.component_id
    root = surface.components[surface.root_component_id]
    if root.kind != "container":
        raise ValueError(
            f"Flow UI surface {surface_id!r} has no container for platform artifacts"
        )
    return root.component_id


def present_flow_ui_artifact(
    state: ExecutionState,
    *,
    kind: FlowUIArtifactKind,
    data: JsonObject,
    source: str,
    artifact_id: str | None = None,
) -> str:
    """Upsert one semantic platform artifact as one real catalog component."""
    if not source.strip():
        raise ValueError("Flow UI artifact source must be non-empty")
    resolved_artifact_id = (
        artifact_id.strip()
        if artifact_id is not None and artifact_id.strip()
        else str(uuid.uuid4())
    )
    page = state.ui_document.pages[state.ui_document.active_page_id]
    surface_id = page.root_surface_id
    surface = state.ui_document.surfaces[surface_id]
    parent_id = _artifact_parent_id(state, surface_id)
    parent = surface.components[parent_id].model_copy(deep=True)
    component_id = f"artifact-{_stable_token(resolved_artifact_id)}"
    is_new = component_id not in surface.components
    if is_new:
        parent.children.append(component_id)

    data_key = _pointer_token(resolved_artifact_id)
    component = FlowUIComponent(
        component_id=component_id,
        type=_COMPONENT_TYPES[kind],
        properties={
            "artifactId": resolved_artifact_id,
            "artifactKind": kind,
            "source": source.strip(),
        },
        bindings={"artifact": f"/content/artifacts/{data_key}"},
        placement=FlowUIResponsivePlacement(
            base=FlowUIPlacement(column_span="full")
        ),
    )
    _ = apply_trusted_ui_commands(
        state,
        [
            FlowUIUpsertComponentsCommand(
                surface_id=surface_id,
                components=[parent, component],
            ),
            FlowUISetDataCommand(
                surface_id=surface_id,
                path=f"/content/artifacts/{data_key}",
                value=data,
            ),
        ],
        transition_id=str(uuid.uuid4()),
        source=f"presenter:{source.strip()}",
    )
    return resolved_artifact_id


__all__ = ["FlowUIArtifactKind", "present_flow_ui_artifact"]
