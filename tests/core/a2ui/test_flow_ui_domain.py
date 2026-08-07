from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from core.a2a.extensions import A2UI_PLATFORM_CATALOG_ID, PLATFORM_UI_SUBMIT_ACTION
from core.models.flow_interface import default_flow_interface_config
from core.state.flow_ui import FlowUIDocument
from core.types import JsonObject, JsonValue, require_json_object


def _document_payload() -> JsonObject:
    return require_json_object(
        deepcopy(
            default_flow_interface_config().template.document.model_dump(mode="python")
        ),
        "FlowUIDocument",
    )


def _object(value: JsonValue) -> JsonObject:
    assert isinstance(value, dict)
    return value


def _grid_document_payload() -> JsonObject:
    """Chat document with an authorable grid parent for placement validation."""
    payload = _document_payload()
    surfaces = _object(payload["surfaces"])
    main = _object(surfaces["main"])
    components = _object(main["components"])
    root = _object(components["root"])
    children = root["children"]
    assert isinstance(children, list)
    children.append("grid-panel")
    components["grid-panel"] = {
        "component_id": "grid-panel",
        "type": "Section",
        "kind": "container",
        "children": ["grid-child"],
        "container_layout": {
            "mode": "grid",
            "grid": {
                "columns_by_band": {"compact": 4, "medium": 8, "wide": 12},
            },
        },
    }
    components["grid-child"] = {
        "component_id": "grid-child",
        "type": "Text",
        "kind": "leaf",
        "placement": {
            "base": {"column_span": 1},
        },
    }
    return payload


def test_default_chat_is_a_regular_editable_flow_ui_document() -> None:
    config = default_flow_interface_config()
    document = config.template.document
    surface = document.surfaces["main"]
    root = surface.components["root"]

    assert config.catalog_id == A2UI_PLATFORM_CATALOG_ID
    assert root.container_layout is not None
    assert root.container_layout.mode == "flex"
    assert root.container_layout.flex is not None
    assert root.container_layout.flex.direction == "column"
    assert root.properties.get("presentation") == "conversation"
    assert surface.components["submit"].actions["press"].name == PLATFORM_UI_SUBMIT_ACTION
    assert surface.data_model.values == {"message": "", "files": []}

    materialized = config.template.materialize(document_id="flow-ui:context-1")
    assert materialized.document_id == "flow-ui:context-1"
    assert materialized.revision == 1
    assert materialized.surfaces["main"].components == surface.components


def test_document_rejects_missing_submit_action() -> None:
    payload = _document_payload()
    surfaces = _object(payload["surfaces"])
    main = _object(surfaces["main"])
    components = _object(main["components"])
    submit = _object(components["submit"])
    submit["actions"] = {}

    with pytest.raises(ValidationError, match="platform.ui.submit"):
        _ = FlowUIDocument.model_validate(payload)


def test_surface_rejects_component_cycles_and_unreachable_nodes() -> None:
    cycle_payload = _document_payload()
    surfaces = _object(cycle_payload["surfaces"])
    main = _object(surfaces["main"])
    components = _object(main["components"])
    form = _object(components["message-form"])
    form["children"] = ["root"]

    with pytest.raises(ValidationError, match="cycle"):
        _ = FlowUIDocument.model_validate(cycle_payload)

    unreachable_payload = _document_payload()
    surfaces = _object(unreachable_payload["surfaces"])
    main = _object(surfaces["main"])
    components = _object(main["components"])
    components["orphan"] = {
        "component_id": "orphan",
        "type": "Text",
        "kind": "leaf",
    }
    with pytest.raises(ValidationError, match="unreachable"):
        _ = FlowUIDocument.model_validate(unreachable_payload)


def test_grid_span_and_reserved_wire_fields_are_validated_in_domain() -> None:
    span_payload = _grid_document_payload()
    surfaces = _object(span_payload["surfaces"])
    main = _object(surfaces["main"])
    components = _object(main["components"])
    child = _object(components["grid-child"])
    placement = _object(child["placement"])
    base = _object(placement["base"])
    base["column_span"] = 13
    with pytest.raises(ValidationError, match="exceeds compact grid"):
        _ = FlowUIDocument.model_validate(span_payload)

    reserved_payload = _document_payload()
    surfaces = _object(reserved_payload["surfaces"])
    main = _object(surfaces["main"])
    components = _object(main["components"])
    header = _object(components["header"])
    header["properties"] = {"component": "Other"}
    with pytest.raises(ValidationError, match="reserved fields"):
        _ = FlowUIDocument.model_validate(reserved_payload)
