"""Publish validator §18.6 for Flow UI documents."""

from __future__ import annotations

import pytest

from core.models.flow_interface import build_default_chat_document, default_flow_interface_config
from core.state.flow_ui_publish import assert_flow_ui_publishable, validate_flow_ui_publish


def test_default_chat_document_is_publishable() -> None:
    document = build_default_chat_document()
    assert validate_flow_ui_publish(document) == []
    assert_flow_ui_publishable(document)


def test_default_interface_config_is_publishable() -> None:
    config = default_flow_interface_config()
    assert_flow_ui_publishable(config.template.document)


def test_missing_submit_is_blocking() -> None:
    document = build_default_chat_document()
    surface = document.surfaces["main"]
    components = dict(surface.components)
    del components["submit"]
    root = components["root"].model_copy(
        update={
            "children": [child for child in components["root"].children if child != "submit"],
        }
    )
    components["root"] = root
    # message-form still references submit child — rebuild form without submit
    form = components["message-form"].model_copy(
        update={"children": ["file-upload", "message-input"]}
    )
    components["message-form"] = form
    broken_surface = surface.model_copy(update={"components": components})
    broken = document.model_copy(update={"surfaces": {"main": broken_surface}})
    problems = validate_flow_ui_publish(broken)
    codes = {item.code for item in problems}
    assert "submit.missing" in codes or "submit.form_unreachable" in codes
    with pytest.raises(ValueError, match="submit"):
        assert_flow_ui_publishable(broken)


def test_permanently_disabled_submit_is_blocking() -> None:
    document = build_default_chat_document()
    surface = document.surfaces["main"]
    submit = surface.components["submit"]
    disabled = submit.model_copy(
        update={
            "properties": {**submit.properties, "disabled": True},
            "bindings": {},
        }
    )
    components = dict(surface.components)
    components["submit"] = disabled
    broken_surface = surface.model_copy(update={"components": components})
    broken = document.model_copy(update={"surfaces": {"main": broken_surface}})
    codes = {item.code for item in validate_flow_ui_publish(broken)}
    assert "submit.disabled_forever" in codes
