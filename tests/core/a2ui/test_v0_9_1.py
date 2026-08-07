from __future__ import annotations

from pathlib import Path

import pytest
from google.protobuf.json_format import MessageToDict

from core.a2a.codec import struct_from_mapping, value_from_json
from core.a2a.extensions import (
    A2UI_EXTENSION_URI,
    A2UI_MIME_TYPE,
    A2UI_PLATFORM_CATALOG_ID,
)
from core.a2ui import A2UI091Codec
from core.a2ui.catalog import get_linnex_platform_catalog
from core.a2ui.catalog_identity import canonical_platform_catalog_id
from core.models.flow_interface import default_flow_interface_config
from core.types import JsonObject, parse_json_object, require_json_object


def _document():
    return default_flow_interface_config().template.materialize(
        document_id="flow-ui:context-1"
    )


def test_snapshot_is_exact_v091_message_sequence_and_standard_a2a_part() -> None:
    codec = A2UI091Codec()
    messages = codec.encode_document_snapshot(_document())

    assert codec.extension_uri == "https://a2ui.org/a2a-extension/a2ui/v0.9.1"
    assert A2UI_EXTENSION_URI == codec.extension_uri
    assert messages[0] == {
        "version": "v0.9.1",
        "createSurface": {
            "surfaceId": "main",
            "catalogId": "https://linnex.io/a2ui/catalog/platform/v1",
            "sendDataModel": True,
        },
    }
    assert messages[1]["version"] == "v0.9.1"
    component_message = messages[1]["updateComponents"]
    assert isinstance(component_message, dict)
    components = component_message["components"]
    assert isinstance(components, list)
    root = components[0]
    assert isinstance(root, dict)
    assert root["id"] == "root"
    assert root["component"] == "PageShell"
    assert root["layout"] == {
        "mode": "flex",
        "flex": {
            "direction": "column",
            "wrap": True,
            "gapToken": "space.0",
            "alignItems": "stretch",
            "justifyContent": "start",
        },
    }
    assert messages[2]["updateDataModel"] == {
        "surfaceId": "main",
        "path": "/",
        "value": {
            "content": {"greeting": "", "suggestedPrompts": []},
            "values": {"message": "", "files": []},
            "system": {"tasks": [], "activeTask": None, "agent": {}},
        },
    }

    part = codec.encode_data_part(messages)
    part_json = MessageToDict(part)
    assert part_json["mediaType"] == A2UI_MIME_TYPE
    assert part_json["metadata"] == {"mimeType": A2UI_MIME_TYPE}
    assert part_json["data"] == messages
    assert codec.decode_data_part(part) == messages


def test_client_action_and_synced_data_model_decode_from_same_a2a_message() -> None:
    codec = A2UI091Codec()
    part = codec.encode_data_part(
        [
            {
                "version": "v0.9.1",
                "action": {
                    "name": "platform.ui.submit",
                    "surfaceId": "main",
                    "sourceComponentId": "submit",
                    "timestamp": "2026-08-04T12:00:00Z",
                    "context": {"formId": "message-form"},
                },
            }
        ]
    )
    metadata: JsonObject = {
        "a2uiClientCapabilities": {
            "v0.9.1": {
                "supportedCatalogIds": [A2UI_PLATFORM_CATALOG_ID],
                "inlineCatalogs": [],
            }
        },
        "a2uiClientDataModel": {
            "version": "v0.9.1",
            "surfaces": {
                "main": {
                    "content": {},
                    "values": {"message": "hello"},
                    "system": {},
                }
            },
        },
    }

    decoded = codec.decode_client_action(part, metadata)
    assert decoded.action.name == "platform.ui.submit"
    assert decoded.action.source_component_id == "submit"
    assert decoded.data_model is not None
    assert decoded.data_model.surfaces["main"]["values"] == {"message": "hello"}
    assert decoded.capabilities is not None
    assert decoded.capabilities.supported_catalog_ids == [A2UI_PLATFORM_CATALOG_ID]


def test_batch_is_sequential_isolates_invalid_message_and_repaints_once() -> None:
    codec = A2UI091Codec()
    original = _document()
    result = codec.apply_agent_message_batch(
        original,
        [
            {
                "version": "v0.9.1",
                "updateComponents": {
                    "surfaceId": "missing",
                    "components": [{"id": "x", "component": "Text"}],
                },
            },
            {
                "version": "v0.9.1",
                "updateDataModel": {
                    "surfaceId": "main",
                    "path": "/values/message",
                    "value": "accepted",
                },
            },
        ],
    )

    assert result.applied_message_count == 1
    assert len(result.errors) == 1
    assert result.errors[0].message_index == 0
    assert result.document.revision == original.revision + 1
    assert result.document.surfaces["main"].data_model.values["message"] == "accepted"


def test_effect_encoder_emits_minimal_component_and_rfc6901_data_updates() -> None:
    codec = A2UI091Codec()
    before = _document()
    after = before.model_copy(deep=True)
    after.surfaces["main"].data_model.values["message"] = "new"
    after.surfaces["main"].components["submit"].properties["label"] = "Continue"

    messages = codec.encode_effect_batch(before, after)
    assert [next(key for key in message if key != "version") for message in messages] == [
        "updateComponents",
        "updateDataModel",
    ]
    component_update = require_json_object(
        messages[0]["updateComponents"], "updateComponents"
    )
    changed_components = component_update["components"]
    assert isinstance(changed_components, list)
    changed_component = require_json_object(changed_components[0], "components[0]")
    assert changed_component["id"] == "submit"
    assert messages[1]["updateDataModel"] == {
        "surfaceId": "main",
        "path": "/values/message",
        "value": "new",
    }


def test_wrong_mime_and_inline_catalogs_fail_closed() -> None:
    codec = A2UI091Codec()
    from a2a.types import Part

    part = Part(
        data=value_from_json([{"version": "v0.9.1", "error": {}}]),
        metadata=struct_from_mapping({"mimeType": "application/json"}),
    )
    with pytest.raises(ValueError, match="MIME"):
        _ = codec.decode_data_part(part)
    with pytest.raises(ValueError, match="inline"):
        _ = codec.validate_client_capabilities(
            {
                "a2uiClientCapabilities": {
                    "v0.9.1": {
                        "supportedCatalogIds": [A2UI_PLATFORM_CATALOG_ID],
                        "inlineCatalogs": [{"catalogId": "untrusted"}],
                    }
                }
            },
            required_catalog_id=A2UI_PLATFORM_CATALOG_ID,
        )


def test_catalog_identity_is_primary_domain_not_current_brand_host() -> None:
    assert canonical_platform_catalog_id("linnex.io") == A2UI_PLATFORM_CATALOG_ID
    assert canonical_platform_catalog_id("humanitec.ru") == (
        "https://humanitec.ru/a2ui/catalog/platform/v1"
    )
    with pytest.raises(ValueError):
        _ = canonical_platform_catalog_id("https://linnex.io/evil")

    manifest = get_linnex_platform_catalog()
    assert manifest["catalog_id"] == A2UI_PLATFORM_CATALOG_ID
    assert manifest["layout_bands"] == {"compact": 4, "medium": 8, "wide": 12}
    assert str(manifest["checksum"]).startswith("sha256:")


def test_pinned_schema_fixtures_are_valid_json() -> None:
    schema_dir = Path(__file__).parents[3] / "core" / "a2ui" / "schemas"
    names = {
        "server_to_client.json",
        "client_to_server.json",
        "client_data_model.json",
        "client_capabilities.json",
        "server_capabilities.json",
        "provenance.json",
    }
    for name in names:
        payload = parse_json_object(
            (schema_dir / name).read_text(encoding="utf-8"), name
        )
        assert payload
