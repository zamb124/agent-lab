"""Pure evaluation of FlowUIComponent.checks against surface data_model values."""

from __future__ import annotations

import re
from collections.abc import Mapping

from core.state.flow_ui import FlowUICheck, FlowUIComponent, FlowUISurface
from core.state.flow_ui_delta import decode_json_pointer
from core.types import JsonObject, JsonValue

_VALUE_BINDING_NAMES = ("value", "values", "files")


def soft_read_json_pointer(root: JsonValue, pointer: str) -> JsonValue | None:
    current: JsonValue = root
    for segment in decode_json_pointer(pointer):
        if not isinstance(current, dict) or segment not in current:
            return None
        current = current[segment]
    return current


def resolve_component_check_value(
    data_model: JsonObject,
    component: FlowUIComponent,
) -> JsonValue | None:
    for name in _VALUE_BINDING_NAMES:
        path = component.bindings.get(name)
        if path is None:
            continue
        return soft_read_json_pointer(data_model, path)
    return None


def is_empty_check_value(value: JsonValue | None) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, bool):
        return value is False
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def _default_check_message(check: FlowUICheck) -> str:
    if check.function == "required":
        return "This field is required"
    if check.function == "email":
        return "Enter a valid email"
    if check.function == "regex":
        return "Value does not match the required pattern"
    if check.function == "minLength":
        return f"Enter at least {check.value} characters"
    if check.function == "maxLength":
        return f"Enter at most {check.value} characters"
    raise ValueError(f"unsupported check function {check.function!r}")


def check_message(check: FlowUICheck) -> str:
    if check.message.strip() != "":
        return check.message
    return _default_check_message(check)


def evaluate_flow_ui_check(check: FlowUICheck, value: JsonValue | None) -> str | None:
    if check.function == "required":
        if is_empty_check_value(value):
            return check_message(check)
        return None

    if is_empty_check_value(value):
        return None

    if check.function == "email":
        if not isinstance(value, str):
            return check_message(check)
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()) is None:
            return check_message(check)
        return None

    if check.function == "regex":
        if check.pattern is None:
            raise ValueError("regex check requires pattern")
        if not isinstance(value, str):
            return check_message(check)
        if re.search(check.pattern, value) is None:
            return check_message(check)
        return None

    if check.function in {"minLength", "maxLength"}:
        if check.value is None:
            raise ValueError(f"{check.function} check requires value")
        text = value if isinstance(value, str) else str(value)
        length = len(text)
        if check.function == "minLength" and length < check.value:
            return check_message(check)
        if check.function == "maxLength" and length > check.value:
            return check_message(check)
        return None

    raise ValueError(f"unsupported check function {check.function!r}")


def evaluate_flow_ui_checks(surface: FlowUISurface) -> dict[str, str]:
    """Return first failing message per component_id. Empty dict means ok."""
    data_model = surface.data_model.model_dump(mode="python")
    errors: dict[str, str] = {}
    for component in surface.components.values():
        if not component.checks:
            continue
        value = resolve_component_check_value(data_model, component)
        for check in component.checks:
            failure = evaluate_flow_ui_check(check, value)
            if failure is not None:
                errors[component.component_id] = failure
                break
    return errors


def evaluate_flow_ui_document_checks(
    surfaces: Mapping[str, FlowUISurface],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for surface_id, surface in surfaces.items():
        errors = evaluate_flow_ui_checks(surface)
        if errors:
            result[surface_id] = errors
    return result
