"""Чтение материализованных Flow UI артефактов из ExecutionState.

Платформенные результаты (skill load, action preview/apply, browser preview,
handoff) больше не отдельная событийная ветка: `present_flow_ui_artifact`
апсертит их как настоящие компоненты каталога и данные по JSON Pointer.
Тесты читают ровно то, что увидит renderer, в порядке ленты артефактов.
"""

from __future__ import annotations

from core.models.base import StrictBaseModel
from core.state import ExecutionState
from core.state.flow_ui import FlowUIComponent, FlowUISurface
from core.state.flow_ui_delta import read_json_pointer
from core.types import JsonObject, require_json_object


class FlowUIArtifactView(StrictBaseModel):
    """Один артефакт так, как он материализован в документе."""

    component_id: str
    component_type: str
    artifact_id: str
    kind: str
    source: str
    data: JsonObject


def active_flow_ui_surface(state: ExecutionState) -> FlowUISurface:
    document = state.ui_document
    page = document.pages[document.active_page_id]
    return document.surfaces[page.root_surface_id]


def _artifact_container(surface: FlowUISurface) -> FlowUIComponent:
    for component in surface.components.values():
        if component.type == "ArtifactFeed" and component.kind == "container":
            return component
    return surface.components[surface.root_component_id]


def flow_ui_artifacts(
    state: ExecutionState, *, kind: str | None = None
) -> list[FlowUIArtifactView]:
    """Артефакты активной surface в порядке отображения."""
    surface = active_flow_ui_surface(state)
    container = _artifact_container(surface)
    data_model = require_json_object(
        surface.data_model.model_dump(mode="python"), "FlowUIDataModel"
    )
    views: list[FlowUIArtifactView] = []
    for child_id in container.children:
        component = surface.components.get(child_id)
        if component is None:
            continue
        artifact_kind = component.properties.get("artifactKind")
        artifact_id = component.properties.get("artifactId")
        if not isinstance(artifact_kind, str) or not isinstance(artifact_id, str):
            continue
        if kind is not None and artifact_kind != kind:
            continue
        pointer = component.bindings["artifact"]
        views.append(
            FlowUIArtifactView(
                component_id=component.component_id,
                component_type=component.type,
                artifact_id=artifact_id,
                kind=artifact_kind,
                source=str(component.properties["source"]),
                data=require_json_object(
                    read_json_pointer(data_model, pointer), f"artifact {artifact_id}"
                ),
            )
        )
    return views


def flow_ui_artifact(state: ExecutionState, artifact_id: str) -> FlowUIArtifactView:
    for view in flow_ui_artifacts(state):
        if view.artifact_id == artifact_id:
            return view
    known = [view.artifact_id for view in flow_ui_artifacts(state)]
    raise AssertionError(f"Flow UI artifact {artifact_id!r} not found; present: {known!r}")


__all__ = [
    "FlowUIArtifactView",
    "active_flow_ui_surface",
    "flow_ui_artifact",
    "flow_ui_artifacts",
]
