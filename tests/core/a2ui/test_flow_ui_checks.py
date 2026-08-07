"""Unit tests for FlowUICheck evaluation parity helper."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.a2ui.v0_9_1 import _decode_component, _encode_component
from core.state.flow_ui import (
    FlowUICheck,
    FlowUIComponent,
    FlowUIDataModel,
    FlowUISurface,
)
from core.state.flow_ui_checks import evaluate_flow_ui_check, evaluate_flow_ui_checks


def test_flow_ui_check_rejects_unknown_function() -> None:
    with pytest.raises(ValidationError):
        _ = FlowUICheck.model_validate({"function": "notARealCheck", "message": ""})


def test_flow_ui_check_required_rejects_extra_payload() -> None:
    with pytest.raises(ValidationError):
        _ = FlowUICheck(function="required", message="", value=1)


def test_evaluate_required_empty_string() -> None:
    check = FlowUICheck(function="required", message="Укажите имя")
    assert evaluate_flow_ui_check(check, "") == "Укажите имя"
    assert evaluate_flow_ui_check(check, "  ") == "Укажите имя"
    assert evaluate_flow_ui_check(check, "ok") is None


def test_a2ui_component_checks_round_trip() -> None:
    component = FlowUIComponent(
        component_id="email",
        type="TextField",
        bindings={"value": "/values/email"},
        checks=[
            FlowUICheck(function="required", message="Email required"),
            FlowUICheck(function="email", message=""),
        ],
    )
    encoded = _encode_component(component)
    assert encoded["checks"] == [
        {"function": "required", "message": "Email required"},
        {"function": "email", "message": ""},
    ]
    decoded = _decode_component(encoded)
    assert decoded.checks == component.checks


def test_evaluate_required_default_message() -> None:
    check = FlowUICheck(function="required", message="")
    assert evaluate_flow_ui_check(check, None) == "This field is required"


def test_evaluate_surface_checks_first_failure_per_component() -> None:
    surface = FlowUISurface(
        surface_id="main",
        components={
            "root": FlowUIComponent(
                component_id="root",
                type="PageShell",
                kind="container",
                children=["name"],
                container_layout={
                    "mode": "stack",
                    "stack": {"direction": "vertical", "gap_token": "space.4"},
                },
            ),
            "name": FlowUIComponent(
                component_id="name",
                type="TextField",
                bindings={"value": "/values/name"},
                checks=[
                    FlowUICheck(function="required", message="Name required"),
                    FlowUICheck(function="minLength", message="Too short", value=3),
                ],
            ),
        },
        data_model=FlowUIDataModel(values={"name": ""}),
    )
    assert evaluate_flow_ui_checks(surface) == {"name": "Name required"}

    surface.data_model = FlowUIDataModel(values={"name": "ab"})
    assert evaluate_flow_ui_checks(surface) == {"name": "Too short"}

    surface.data_model = FlowUIDataModel(values={"name": "abc"})
    assert evaluate_flow_ui_checks(surface) == {}
