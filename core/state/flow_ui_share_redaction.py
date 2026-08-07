"""Viewer-specific Flow UI document redaction for share grants.

Durable ``ExecutionState.ui_document`` is never mutated. Redaction produces a
self-consistent copy for A2A snapshot serialization to a scoped viewer.
"""

from __future__ import annotations

from copy import deepcopy

from core.models.flow_ui_share import FlowUIShareGrant
from core.state.flow_ui import FlowUIDataModel, FlowUIDocument
from core.state.flow_ui_delta import delete_json_pointer, read_json_pointer
from core.types import JsonObject, JsonValue, require_json_object


def _normalize_redacted_path(path: str) -> str:
    if path.strip() == "":
        raise ValueError("Flow UI share redacted path must be a non-empty string")
    normalized = path.strip()
    if not normalized.startswith("/"):
        raise ValueError(f"Flow UI share redacted path must be a JSON Pointer: {path!r}")
    if not (
        normalized == "/values"
        or normalized.startswith("/values/")
        or normalized == "/content"
        or normalized.startswith("/content/")
    ):
        raise ValueError(
            "Flow UI share redacted paths must target /values or /content namespaces"
        )
    return normalized


def validate_share_redacted_paths(paths: list[str]) -> list[str]:
    normalized = [_normalize_redacted_path(path) for path in paths]
    return list(dict.fromkeys(normalized))


def path_is_redacted(path: str, redacted_paths: list[str]) -> bool:
    for root in redacted_paths:
        if path == root or path.startswith(f"{root}/"):
            return True
    return False


def _delete_if_present(payload: JsonObject, pointer: str) -> JsonObject:
    try:
        _ = read_json_pointer(payload, pointer)
    except ValueError:
        return payload
    deleted = delete_json_pointer(payload, pointer)
    return require_json_object(deleted, "FlowUIDataModel after redaction")


def apply_share_redaction(
    document: FlowUIDocument,
    grant: FlowUIShareGrant,
) -> FlowUIDocument:
    """Return a viewer copy with forbidden value/content paths removed."""
    redacted_paths = validate_share_redacted_paths(list(grant.redacted_value_paths))
    if not redacted_paths:
        return document.model_copy(deep=True)

    redacted = document.model_copy(deep=True)
    for surface in redacted.surfaces.values():
        payload = require_json_object(
            surface.data_model.model_dump(mode="python"),
            "FlowUIDataModel",
        )
        for pointer in redacted_paths:
            payload = _delete_if_present(payload, pointer)
        surface.data_model = FlowUIDataModel.model_validate(payload)

    global_payload = require_json_object(
        redacted.global_data_model.model_dump(mode="python"),
        "FlowUIDataModel.global",
    )
    for pointer in redacted_paths:
        global_payload = _delete_if_present(global_payload, pointer)
    redacted.global_data_model = FlowUIDataModel.model_validate(global_payload)
    return FlowUIDocument.model_validate(redacted.model_dump(mode="python"))


def assert_share_mutation_allowed(
    grant: FlowUIShareGrant,
    values_by_surface: dict[str, JsonObject],
) -> None:
    """Fail closed when a share collaborator writes a redacted path."""
    redacted_paths = validate_share_redacted_paths(list(grant.redacted_value_paths))
    if not redacted_paths:
        return

    def walk(value: JsonValue, *, path: str) -> None:
        if path_is_redacted(path, redacted_paths):
            raise PermissionError(
                f"Flow UI share grant forbids client writes under {path!r}"
            )
        if isinstance(value, dict):
            for key, child in value.items():
                segment = str(key).replace("~", "~0").replace("/", "~1")
                walk(child, path=f"{path}/{segment}")

    for values in values_by_surface.values():
        walk(deepcopy(values), path="/values")


__all__ = [
    "apply_share_redaction",
    "assert_share_mutation_allowed",
    "path_is_redacted",
    "validate_share_redacted_paths",
]
