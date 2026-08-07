"""Atomic semantic Flow UI commands and RFC 6901 data updates."""

from __future__ import annotations

from copy import deepcopy
from typing import final

from pydantic import Field

from core.models.base import StrictBaseModel
from core.state.flow_ui import (
    FlowUICommand,
    FlowUICreateSurfaceCommand,
    FlowUIDeleteComponentsCommand,
    FlowUIDeleteDataCommand,
    FlowUIDocument,
    FlowUINavigateCommand,
    FlowUIReplaceSurfaceCommand,
    FlowUISetDataCommand,
    FlowUISurface,
    FlowUIUpsertComponentsCommand,
)
from core.types import JsonObject, JsonValue, require_json_object


@final
class FlowUIRevisionConflictError(ValueError):
    def __init__(self, *, expected: int, actual: int) -> None:
        self.expected: int = expected
        self.actual: int = actual
        super().__init__(f"Flow UI revision conflict: expected {expected}, actual {actual}")


class FlowUIDeltaResult(StrictBaseModel):
    document: FlowUIDocument
    changed: bool
    applied_command_count: int = Field(ge=0)


def decode_json_pointer(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must be empty or start with '/'")
    return [segment.replace("~1", "/").replace("~0", "~") for segment in pointer[1:].split("/")]


def _parse_index(segment: str, *, size: int, allow_end: bool) -> int:
    if segment == "-" and allow_end:
        return size
    if segment == "" or (len(segment) > 1 and segment.startswith("0")):
        raise ValueError(f"Invalid JSON Pointer array index: {segment!r}")
    try:
        index = int(segment)
    except ValueError as exc:
        raise ValueError(f"Invalid JSON Pointer array index: {segment!r}") from exc
    upper = size if allow_end else size - 1
    if index < 0 or index > upper:
        raise ValueError(f"JSON Pointer array index out of range: {segment!r}")
    return index


def read_json_pointer(root: JsonValue, pointer: str) -> JsonValue:
    """Resolve one existing RFC 6901 location; a missing location is an error."""
    current: JsonValue = root
    for segment in decode_json_pointer(pointer):
        if isinstance(current, dict):
            if segment not in current:
                raise ValueError(f"JSON Pointer {pointer!r} has no member {segment!r}")
            current = current[segment]
        elif isinstance(current, list):
            current = current[_parse_index(segment, size=len(current), allow_end=False)]
        else:
            raise ValueError(f"JSON Pointer {pointer!r} traverses scalar at {segment!r}")
    return current


def set_json_pointer(root: JsonValue, pointer: str, value: JsonValue) -> JsonValue:
    segments = decode_json_pointer(pointer)
    if not segments:
        return deepcopy(value)
    current: JsonValue = root
    for segment in segments[:-1]:
        if isinstance(current, dict):
            if segment not in current:
                current[segment] = {}
            current = current[segment]
        elif isinstance(current, list):
            current = current[_parse_index(segment, size=len(current), allow_end=False)]
        else:
            raise ValueError(f"JSON Pointer traverses scalar at {segment!r}")
    leaf = segments[-1]
    if isinstance(current, dict):
        current[leaf] = deepcopy(value)
    elif isinstance(current, list):
        index = _parse_index(leaf, size=len(current), allow_end=True)
        if index == len(current):
            current.append(deepcopy(value))
        else:
            current[index] = deepcopy(value)
    else:
        raise ValueError("JSON Pointer target parent is a scalar")
    return root


def delete_json_pointer(root: JsonValue, pointer: str) -> JsonValue:
    segments = decode_json_pointer(pointer)
    if not segments:
        raise ValueError("Deleting the complete data model is forbidden")
    current: JsonValue = root
    for segment in segments[:-1]:
        if isinstance(current, dict):
            if segment not in current:
                return root
            current = current[segment]
        elif isinstance(current, list):
            current = current[_parse_index(segment, size=len(current), allow_end=False)]
        else:
            return root
    leaf = segments[-1]
    if isinstance(current, dict):
        _ = current.pop(leaf, None)
    elif isinstance(current, list):
        index = _parse_index(leaf, size=len(current), allow_end=False)
        _ = current.pop(index)
    return root


def _component_subtree(surface: FlowUISurface, component_id: str) -> set[str]:
    collected: set[str] = set()
    pending = [component_id]
    while pending:
        current = pending.pop()
        if current in collected or current not in surface.components:
            continue
        collected.add(current)
        pending.extend(surface.components[current].children)
    return collected


def _delete_components(surface: FlowUISurface, component_ids: list[str]) -> None:
    """Удалить узлы вместе с поддеревом и отцепить их от оставшихся родителей.

    Компонент существует только как узел дерева surface, поэтому удаление
    обязано снимать и рёбра: иначе любая одиночная delete-команда оставляла бы
    dangling reference и не проходила domain validation.
    """
    if surface.root_component_id in component_ids:
        raise ValueError("Deleting a surface root component is forbidden")
    removed: set[str] = set()
    for component_id in component_ids:
        removed |= _component_subtree(surface, component_id)
    for component_id in removed:
        _ = surface.components.pop(component_id, None)
    for component in surface.components.values():
        if any(child in removed for child in component.children):
            component.children = [
                child for child in component.children if child not in removed
            ]


def _data_model_payload(document: FlowUIDocument, surface_id: str | None) -> JsonObject:
    model = (
        document.global_data_model
        if surface_id is None
        else document.surfaces[surface_id].data_model
    )
    return require_json_object(model.model_dump(mode="python"), "FlowUIDataModel")


def _replace_data_model(
    document: FlowUIDocument,
    *,
    surface_id: str | None,
    payload: JsonObject,
) -> None:
    from core.state.flow_ui import FlowUIDataModel

    model = FlowUIDataModel.model_validate(payload)
    if surface_id is None:
        document.global_data_model = model
    else:
        if surface_id not in document.surfaces:
            raise ValueError(f"Unknown Flow UI surface: {surface_id!r}")
        document.surfaces[surface_id].data_model = model


def apply_flow_ui_commands(
    document: FlowUIDocument,
    commands: list[FlowUICommand],
    *,
    expected_revision: int | None = None,
    client_mutation_id: str | None = None,
    allow_system_data: bool = True,
) -> FlowUIDeltaResult:
    if client_mutation_id is not None:
        if client_mutation_id.strip() == "":
            raise ValueError("client_mutation_id must be non-empty")
        if client_mutation_id == document.last_accepted_client_mutation_id:
            return FlowUIDeltaResult(
                document=document.model_copy(deep=True),
                changed=False,
                applied_command_count=0,
            )
    if expected_revision is not None and expected_revision != document.revision:
        raise FlowUIRevisionConflictError(expected=expected_revision, actual=document.revision)
    if not commands:
        return FlowUIDeltaResult(
            document=document.model_copy(deep=True),
            changed=False,
            applied_command_count=0,
        )

    updated = document.model_copy(deep=True)
    for command in commands:
        if isinstance(command, FlowUIUpsertComponentsCommand):
            surface = updated.surfaces.get(command.surface_id)
            if surface is None:
                raise ValueError(f"Unknown Flow UI surface: {command.surface_id!r}")
            for component in command.components:
                surface.components[component.component_id] = component.model_copy(deep=True)
        elif isinstance(command, FlowUIDeleteComponentsCommand):
            surface = updated.surfaces.get(command.surface_id)
            if surface is None:
                raise ValueError(f"Unknown Flow UI surface: {command.surface_id!r}")
            _delete_components(surface, command.component_ids)
        elif isinstance(command, FlowUISetDataCommand):
            if not allow_system_data and command.path.startswith("/system"):
                raise ValueError("Client mutations cannot write /system")
            payload = _data_model_payload(updated, command.surface_id)
            _ = set_json_pointer(payload, command.path, command.value)
            _replace_data_model(updated, surface_id=command.surface_id, payload=payload)
        elif isinstance(command, FlowUIDeleteDataCommand):
            if not allow_system_data and command.path.startswith("/system"):
                raise ValueError("Client mutations cannot delete /system")
            payload = _data_model_payload(updated, command.surface_id)
            _ = delete_json_pointer(payload, command.path)
            _replace_data_model(updated, surface_id=command.surface_id, payload=payload)
        elif isinstance(command, FlowUINavigateCommand):
            if command.page_id not in updated.pages:
                raise ValueError(f"Unknown Flow UI page: {command.page_id!r}")
            updated.active_page_id = command.page_id
        elif isinstance(command, FlowUICreateSurfaceCommand):
            if command.surface.surface_id in updated.surfaces:
                raise ValueError(
                    f"Flow UI surface already exists: {command.surface.surface_id!r}"
                )
            updated.surfaces[command.surface.surface_id] = command.surface.model_copy(
                deep=True
            )
        elif isinstance(command, FlowUIReplaceSurfaceCommand):
            updated.surfaces[command.surface.surface_id] = command.surface.model_copy(deep=True)
        else:
            if any(
                page.root_surface_id == command.surface_id
                for page in updated.pages.values()
            ):
                raise ValueError("Deleting a page root surface is forbidden")
            _ = updated.surfaces.pop(command.surface_id, None)

    updated.revision += 1
    if client_mutation_id is not None:
        updated.last_accepted_client_mutation_id = client_mutation_id
    validated = FlowUIDocument.model_validate(updated.model_dump(mode="python"))
    return FlowUIDeltaResult(
        document=validated,
        changed=True,
        applied_command_count=len(commands),
    )


__all__ = [
    "FlowUIDeltaResult",
    "FlowUIRevisionConflictError",
    "apply_flow_ui_commands",
    "decode_json_pointer",
    "delete_json_pointer",
    "read_json_pointer",
    "set_json_pointer",
]
