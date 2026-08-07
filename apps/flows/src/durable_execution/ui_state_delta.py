"""Semantic ExecutionStateDelta helpers for Flow UI document fields."""

from __future__ import annotations

from copy import deepcopy

from apps.flows.src.durable_execution.models import (
    ExecutionStateDelta,
    UIClientMutationRef,
    UIComponentPlacementPatch,
    UIComponentPropertyPatch,
    UIContainerLayoutPatch,
    UIDataPathValue,
)
from core.state.flow_ui import (
    FlowUIComponent,
    FlowUIDataModel,
    FlowUIDocument,
    FlowUIInteraction,
    FlowUIResponsivePlacement,
)
from core.state.flow_ui_delta import delete_json_pointer, set_json_pointer
from core.types import JsonObject, JsonValue, require_json_object

_UI_OWNED_STATE_FIELDS = frozenset(
    {
        "ui_document",
        "ui_interaction",
        "ui_last_accepted_client_mutation_id",
        "ui_last_accepted_client_mutation_hash",
    }
)


def _dump_component(component: FlowUIComponent) -> JsonObject:
    return require_json_object(component.model_dump(mode="json"), "FlowUIComponent")


def _component_body_changed(before: FlowUIComponent, after: FlowUIComponent) -> bool:
    before_dump = _dump_component(before)
    after_dump = _dump_component(after)
    for key in ("properties", "container_layout", "placement"):
        _ = before_dump.pop(key, None)
        _ = after_dump.pop(key, None)
    return before_dump != after_dump


def _diff_data_model(
    *,
    surface_id: str | None,
    before: FlowUIDataModel,
    after: FlowUIDataModel,
) -> list[UIDataPathValue]:
    patches: list[UIDataPathValue] = []
    before_json = require_json_object(before.model_dump(mode="json"), "before data")
    after_json = require_json_object(after.model_dump(mode="json"), "after data")
    for key in ("values", "content", "system"):
        before_value = before_json.get(key)
        after_value = after_json.get(key)
        if before_value != after_value:
            patches.append(
                UIDataPathValue(
                    surface_id=surface_id,
                    path=f"/{key}",
                    value=deepcopy(after_value),
                )
            )
    return patches


def build_ui_document_delta(
    before: FlowUIDocument,
    after: FlowUIDocument,
) -> ExecutionStateDelta:
    """Build semantic UI fields for one document transition."""
    if before.document_id != after.document_id:
        raise ValueError("Flow UI document_id cannot change via semantic delta")
    if before.template_version != after.template_version:
        raise ValueError("Flow UI template_version cannot change via semantic delta")
    if before.catalog_id != after.catalog_id:
        raise ValueError("Flow UI catalog_id cannot change via semantic delta")

    delta = ExecutionStateDelta()
    before_surfaces = before.surfaces
    after_surfaces = after.surfaces

    for surface_id in sorted(set(before_surfaces) - set(after_surfaces)):
        delta.ui_surfaces_delete.append(surface_id)
    for surface_id, after_surface in after_surfaces.items():
        before_surface = before_surfaces.get(surface_id)
        if before_surface is None:
            delta.ui_surfaces_upsert[surface_id] = after_surface.model_copy(deep=True)
            continue
        if before_surface.root_component_id != after_surface.root_component_id:
            delta.ui_surfaces_upsert[surface_id] = after_surface.model_copy(deep=True)
            continue

        deleted_ids = sorted(
            set(before_surface.components) - set(after_surface.components)
        )
        if deleted_ids:
            delta.ui_components_delete[surface_id] = deleted_ids

        upserts: dict[str, FlowUIComponent] = {}
        for component_id, after_component in after_surface.components.items():
            before_component = before_surface.components.get(component_id)
            if before_component is None or _component_body_changed(
                before_component, after_component
            ):
                upserts[component_id] = after_component.model_copy(deep=True)
                continue
            if before_component.properties != after_component.properties:
                delta.ui_component_properties_set.append(
                    UIComponentPropertyPatch(
                        surface_id=surface_id,
                        component_id=component_id,
                        properties=deepcopy(after_component.properties),
                    )
                )
            if before_component.container_layout != after_component.container_layout:
                if after_component.container_layout is None:
                    raise ValueError(
                        f"container layout unset for {component_id!r} requires "
                        + "explicit ui_container_layout_unset"
                    )
                delta.ui_container_layout_set.append(
                    UIContainerLayoutPatch(
                        surface_id=surface_id,
                        component_id=component_id,
                        layout=after_component.container_layout.model_copy(deep=True),
                    )
                )
            if before_component.placement != after_component.placement:
                delta.ui_component_placement_set.append(
                    UIComponentPlacementPatch(
                        surface_id=surface_id,
                        component_id=component_id,
                        placement=after_component.placement.model_copy(deep=True),
                    )
                )
        if upserts:
            delta.ui_components_upsert[surface_id] = upserts

        delta.ui_data_set.extend(
            _diff_data_model(
                surface_id=surface_id,
                before=before_surface.data_model,
                after=after_surface.data_model,
            )
        )

    delta.ui_data_set.extend(
        _diff_data_model(
            surface_id=None,
            before=before.global_data_model,
            after=after.global_data_model,
        )
    )

    before_pages = before.pages
    after_pages = after.pages
    for page_id in sorted(set(before_pages) - set(after_pages)):
        delta.ui_pages_delete.append(page_id)
    for page_id, after_page in after_pages.items():
        before_page = before_pages.get(page_id)
        if before_page is None or before_page != after_page:
            delta.ui_pages_upsert[page_id] = after_page.model_copy(deep=True)

    if before.active_page_id != after.active_page_id:
        delta.ui_active_page_set = after.active_page_id

    before_view = before.session_view_state
    after_view = after.session_view_state
    for key, value in after_view.items():
        if before_view.get(key) != value:
            delta.ui_session_view_state_set[key] = deepcopy(value)
    for key in before_view:
        if key not in after_view:
            delta.ui_session_view_state_delete.append(key)

    if before.revision != after.revision:
        delta.ui_revision_set = after.revision

    return delta


def apply_ui_document_delta(
    document: FlowUIDocument,
    delta: ExecutionStateDelta,
) -> FlowUIDocument:
    """Apply semantic UI fields onto a FlowUIDocument copy."""
    next_document = document.model_copy(deep=True)

    for surface_id in delta.ui_surfaces_delete:
        if surface_id not in next_document.surfaces:
            raise ValueError(f"Unknown Flow UI surface delete: {surface_id!r}")
        _ = next_document.surfaces.pop(surface_id)

    for surface_id, surface in delta.ui_surfaces_upsert.items():
        next_document.surfaces[surface_id] = surface.model_copy(deep=True)

    for surface_id, component_ids in delta.ui_components_delete.items():
        surface = next_document.surfaces.get(surface_id)
        if surface is None:
            raise ValueError(f"Unknown Flow UI surface for delete: {surface_id!r}")
        for component_id in component_ids:
            if component_id not in surface.components:
                raise ValueError(
                    f"Unknown Flow UI component delete: {surface_id}/{component_id}"
                )
            _ = surface.components.pop(component_id)

    for surface_id, components in delta.ui_components_upsert.items():
        surface = next_document.surfaces.get(surface_id)
        if surface is None:
            raise ValueError(f"Unknown Flow UI surface for upsert: {surface_id!r}")
        for component_id, component in components.items():
            if component.component_id != component_id:
                raise ValueError("component map key must equal component_id")
            surface.components[component_id] = component.model_copy(deep=True)

    for patch in delta.ui_component_properties_set:
        component = _require_component(next_document, patch.surface_id, patch.component_id)
        component.properties = deepcopy(patch.properties)

    for patch in delta.ui_component_properties_delete:
        component = _require_component(next_document, patch.surface_id, patch.component_id)
        for key in patch.property_keys:
            _ = component.properties.pop(key, None)

    for patch in delta.ui_container_layout_set:
        component = _require_component(next_document, patch.surface_id, patch.component_id)
        component.container_layout = patch.layout.model_copy(deep=True)

    for unset in delta.ui_container_layout_unset:
        component = _require_component(next_document, unset.surface_id, unset.component_id)
        component.container_layout = None

    for patch in delta.ui_component_placement_set:
        component = _require_component(next_document, patch.surface_id, patch.component_id)
        component.placement = patch.placement.model_copy(deep=True)

    for unset in delta.ui_component_placement_unset:
        component = _require_component(next_document, unset.surface_id, unset.component_id)
        component.placement = FlowUIResponsivePlacement()

    for item in delta.ui_data_set:
        _apply_data_path(next_document, item.surface_id, item.path, item.value)

    for item in delta.ui_data_delete:
        _delete_data_path(next_document, item.surface_id, item.path)

    for page_id in delta.ui_pages_delete:
        if page_id not in next_document.pages:
            raise ValueError(f"Unknown Flow UI page delete: {page_id!r}")
        _ = next_document.pages.pop(page_id)

    for page_id, page in delta.ui_pages_upsert.items():
        if page.page_id != page_id:
            raise ValueError("page map key must equal page_id")
        next_document.pages[page_id] = page.model_copy(deep=True)

    if delta.ui_active_page_set is not None:
        next_document.active_page_id = delta.ui_active_page_set

    for key in delta.ui_session_view_state_delete:
        _ = next_document.session_view_state.pop(key, None)
    next_document.session_view_state.update(deepcopy(delta.ui_session_view_state_set))

    if delta.ui_revision_set is not None:
        next_document.revision = delta.ui_revision_set

    return FlowUIDocument.model_validate(next_document.model_dump(mode="python"))


def _require_component(
    document: FlowUIDocument,
    surface_id: str,
    component_id: str,
) -> FlowUIComponent:
    surface = document.surfaces.get(surface_id)
    if surface is None:
        raise ValueError(f"Unknown Flow UI surface: {surface_id!r}")
    component = surface.components.get(component_id)
    if component is None:
        raise ValueError(f"Unknown Flow UI component: {surface_id}/{component_id}")
    return component


def _data_model_for(
    document: FlowUIDocument,
    surface_id: str | None,
) -> FlowUIDataModel:
    if surface_id is None:
        return document.global_data_model
    surface = document.surfaces.get(surface_id)
    if surface is None:
        raise ValueError(f"Unknown Flow UI surface: {surface_id!r}")
    return surface.data_model


def _apply_data_path(
    document: FlowUIDocument,
    surface_id: str | None,
    path: str,
    value: JsonValue,
) -> None:
    model = _data_model_for(document, surface_id)
    payload = require_json_object(model.model_dump(mode="python"), "FlowUIDataModel")
    updated = set_json_pointer(payload, path, value)
    replaced = FlowUIDataModel.model_validate(updated)
    if surface_id is None:
        document.global_data_model = replaced
    else:
        document.surfaces[surface_id].data_model = replaced


def _delete_data_path(
    document: FlowUIDocument,
    surface_id: str | None,
    path: str,
) -> None:
    model = _data_model_for(document, surface_id)
    payload = require_json_object(model.model_dump(mode="python"), "FlowUIDataModel")
    updated = delete_json_pointer(payload, path)
    replaced = FlowUIDataModel.model_validate(updated)
    if surface_id is None:
        document.global_data_model = replaced
    else:
        document.surfaces[surface_id].data_model = replaced


def populate_ui_state_fields(
    delta: ExecutionStateDelta,
    *,
    before_interaction: FlowUIInteraction | None,
    after_interaction: FlowUIInteraction | None,
    before_mutation_id: str | None,
    after_mutation_id: str | None,
    before_mutation_hash: str | None,
    after_mutation_hash: str | None,
) -> None:
    if after_interaction is None and before_interaction is not None:
        delta.ui_interaction_unset = True
    elif after_interaction is not None and after_interaction != before_interaction:
        delta.ui_interaction_set = after_interaction.model_copy(deep=True)

    if (
        after_mutation_id != before_mutation_id
        or after_mutation_hash != before_mutation_hash
    ):
        delta.ui_last_client_mutation_set = UIClientMutationRef(
            mutation_id=after_mutation_id,
            mutation_hash=after_mutation_hash,
        )


def strip_ui_owned_fields(fields_set: dict[str, JsonValue]) -> None:
    for key in _UI_OWNED_STATE_FIELDS:
        _ = fields_set.pop(key, None)


__all__ = [
    "apply_ui_document_delta",
    "build_ui_document_delta",
    "populate_ui_state_fields",
    "strip_ui_owned_fields",
]
