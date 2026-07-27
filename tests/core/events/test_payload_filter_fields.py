"""Unit: derive_filter_fields + catalog filter_fields SSOT."""

from __future__ import annotations

from enum import StrEnum

import pytest
from pydantic import BaseModel, Field

from core.events.payload_filter_fields import (
    PlatformEventFilterField,
    derive_filter_fields,
    ensure_catalog_filter_fields,
    filter_field_by_path,
    validate_event_filters_against_fields,
)
from core.events.registry import (
    PlatformEventCatalogEntry,
    catalog_entry_for_event_type,
    platform_event_catalog,
    register_platform_event,
)
from core.types import JsonObject
from core.worktracker import events as _worktracker_events
from core.worktracker.events import WORK_ITEM_COMMENT_CREATED

_ = _worktracker_events


class _NestedChild(BaseModel):
    role: str
    score: int = 0


class _NestedPayload(BaseModel):
    entity_id: str
    child: _NestedChild
    tags: list[str] = Field(default_factory=list)
    files: list[_NestedChild] = Field(default_factory=list)


def test_derive_nested_enum_and_scalar_array() -> None:
    class Kind(StrEnum):
        A = "a"
        B = "b"

    class Payload(BaseModel):
        kind: Kind
        nested: _NestedChild
        labels: list[str] = Field(default_factory=list)
        items: list[_NestedChild] = Field(default_factory=list)

    fields = derive_filter_fields(Payload.model_json_schema())
    by_path = {field.path: field for field in fields}
    assert "kind" in by_path
    assert by_path["kind"].value_kind == "enum"
    assert by_path["kind"].enum_values == ["a", "b"]
    assert by_path["kind"].ops == ["eq", "ne"]
    assert "nested.role" in by_path
    assert by_path["nested.role"].value_kind == "string"
    assert "contains" in by_path["nested.role"].ops
    assert "nested.score" in by_path
    assert by_path["nested.score"].value_kind == "integer"
    assert "labels" in by_path
    assert "contains" in by_path["labels"].ops
    assert "items" not in by_path
    assert "items.role" not in by_path


def test_derive_skips_array_of_objects() -> None:
    fields = derive_filter_fields(_NestedPayload.model_json_schema())
    paths = {field.path for field in fields}
    assert "entity_id" in paths
    assert "child.role" in paths
    assert "tags" in paths
    assert "files" not in paths
    assert "files.role" not in paths


def test_validate_filters_against_fields() -> None:
    fields = [
        PlatformEventFilterField(
            path="kind",
            label="kind",
            value_kind="enum",
            enum_values=["a", "b"],
            ops=["eq", "ne"],
        ),
        PlatformEventFilterField(
            path="title",
            label="title",
            value_kind="string",
            ops=["eq", "ne", "contains"],
        ),
    ]
    validate_event_filters_against_fields([("kind", "eq", "a")], fields)
    with pytest.raises(ValueError, match="unknown filter path"):
        validate_event_filters_against_fields([("missing", "eq", "x")], fields)
    with pytest.raises(ValueError, match="not allowed"):
        validate_event_filters_against_fields([("kind", "contains", "a")], fields)
    with pytest.raises(ValueError, match="not in enum"):
        validate_event_filters_against_fields([("kind", "eq", "z")], fields)


def test_comment_created_catalog_has_comment_role_enum() -> None:
    entry = catalog_entry_for_event_type(WORK_ITEM_COMMENT_CREATED)
    assert entry is not None
    role = next((f for f in entry.filter_fields if f.path == "comment.role"), None)
    assert role is not None
    assert role.value_kind == "enum"
    assert role.enum_values is not None
    assert "operator" in role.enum_values


def test_new_register_appears_in_catalog_with_filter_fields(unique_id: str) -> None:
    event_type = f"test/auto_{unique_id.replace('-', '_').lower()}/happened"

    class AutoPayload(BaseModel):
        auto_id: str
        flag: bool = False

    register_platform_event(event_type, AutoPayload, description="Auto catalog probe.")
    entry = next(item for item in platform_event_catalog() if item.event_type == event_type)
    paths = {field.path for field in entry.filter_fields}
    assert "auto_id" in paths
    assert "flag" in paths
    flag = next(field for field in entry.filter_fields if field.path == "flag")
    assert flag.value_kind == "boolean"


def test_catalog_entry_auto_heal_filter_fields() -> None:
    class HealPayload(BaseModel):
        heal_id: str

    schema = HealPayload.model_json_schema()
    stale = PlatformEventCatalogEntry(
        event_type="test/heal/created",
        description="stale",
        payload_schema=schema,
        filter_fields=[],
    )
    healed = stale.with_ensured_filter_fields()
    assert any(field.path == "heal_id" for field in healed.filter_fields)


def test_derive_discriminated_union_emits_variant_leaves() -> None:
    from typing import Annotated, Literal

    from pydantic import Discriminator

    class QueueAssignment(BaseModel):
        assignee_kind: Literal["queue"] = "queue"
        work_queue_id: str
        claimed_by_user_id: str | None = None

    class UsersAssignment(BaseModel):
        assignee_kind: Literal["users"] = "users"
        user_ids: list[str] = Field(default_factory=list)

    class Payload(BaseModel):
        assignment: Annotated[
            QueueAssignment | UsersAssignment,
            Discriminator("assignee_kind"),
        ]

    fields = derive_filter_fields(Payload.model_json_schema())
    paths = {field.path for field in fields}
    assert "assignment.assignee_kind" in paths
    assert "assignment.work_queue_id" in paths
    assert "assignment.user_ids" in paths
    kind = next(field for field in fields if field.path == "assignment.assignee_kind")
    assert kind.value_kind == "enum"
    assert kind.enum_values is not None
    assert set(kind.enum_values) >= {"queue", "users"}


def test_ensure_catalog_filter_fields_passthrough_when_present() -> None:
    existing = [
        PlatformEventFilterField(
            path="kept",
            label="kept",
            value_kind="string",
            ops=["eq", "ne", "contains"],
        )
    ]
    healed = ensure_catalog_filter_fields(
        "test/keep/created",
        "desc",
        {"type": "object", "properties": {"other": {"type": "string"}}},
        existing,
    )
    assert healed is existing
    assert healed[0].path == "kept"


def test_filter_field_by_path_found_and_missing() -> None:
    fields = [
        PlatformEventFilterField(
            path="title",
            label="title",
            value_kind="string",
            ops=["eq", "ne", "contains"],
        )
    ]
    assert filter_field_by_path(fields, "title") is fields[0]
    assert filter_field_by_path(fields, "missing") is None


def test_validate_empty_fields_allows_empty_filters() -> None:
    validate_event_filters_against_fields([], [])


def test_validate_empty_fields_rejects_nonempty_filters() -> None:
    with pytest.raises(ValueError, match="no filterable fields"):
        validate_event_filters_against_fields([("x", "eq", "y")], [])


def test_validate_boolean_integer_number_string_types() -> None:
    fields = [
        PlatformEventFilterField(
            path="flag", label="flag", value_kind="boolean", ops=["eq", "ne"]
        ),
        PlatformEventFilterField(
            path="score", label="score", value_kind="integer", ops=["eq", "ne"]
        ),
        PlatformEventFilterField(
            path="ratio", label="ratio", value_kind="number", ops=["eq", "ne"]
        ),
        PlatformEventFilterField(
            path="title",
            label="title",
            value_kind="string",
            ops=["eq", "ne", "contains"],
        ),
    ]
    validate_event_filters_against_fields(
        [
            ("flag", "eq", True),
            ("score", "eq", 3),
            ("ratio", "eq", 1.5),
            ("title", "eq", "ok"),
        ],
        fields,
    )
    with pytest.raises(ValueError, match="expects boolean"):
        validate_event_filters_against_fields([("flag", "eq", "true")], fields)
    with pytest.raises(ValueError, match="expects integer"):
        validate_event_filters_against_fields([("score", "eq", True)], fields)
    with pytest.raises(ValueError, match="expects integer"):
        validate_event_filters_against_fields([("score", "eq", 1.5)], fields)
    with pytest.raises(ValueError, match="expects integer"):
        validate_event_filters_against_fields([("score", "eq", "1")], fields)
    with pytest.raises(ValueError, match="expects number"):
        validate_event_filters_against_fields([("ratio", "eq", True)], fields)
    with pytest.raises(ValueError, match="expects number"):
        validate_event_filters_against_fields([("ratio", "eq", "1.5")], fields)
    with pytest.raises(ValueError, match="expects string"):
        validate_event_filters_against_fields([("title", "eq", 1)], fields)


def test_validate_enum_values_missing_raises() -> None:
    fields = [
        PlatformEventFilterField(
            path="kind",
            label="kind",
            value_kind="enum",
            enum_values=None,
            ops=["eq", "ne"],
        )
    ]
    with pytest.raises(ValueError, match="enum_values missing"):
        validate_event_filters_against_fields([("kind", "eq", "a")], fields)


def test_with_ensured_filter_fields_identity_when_already_populated() -> None:
    fields = [
        PlatformEventFilterField(
            path="heal_id",
            label="heal_id",
            value_kind="string",
            ops=["eq", "ne", "contains"],
        )
    ]
    entry = PlatformEventCatalogEntry(
        event_type="test/heal/identity",
        description="populated",
        payload_schema={"type": "object", "properties": {"heal_id": {"type": "string"}}},
        filter_fields=fields,
    )
    ensured = entry.with_ensured_filter_fields()
    assert ensured is entry


def test_derive_legacy_definitions_key() -> None:
    schema: JsonObject = {
        "type": "object",
        "properties": {
            "child": {"$ref": "#/definitions/Child"},
        },
        "definitions": {
            "Child": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            }
        },
    }
    fields = derive_filter_fields(schema)
    assert {field.path for field in fields} == {"child.name"}


def test_derive_array_of_enum_and_array_of_ints() -> None:
    class Tag(StrEnum):
        VIP = "vip"
        B2B = "b2b"

    class Payload(BaseModel):
        tags: list[Tag] = Field(default_factory=list)
        scores: list[int] = Field(default_factory=list)

    fields = derive_filter_fields(Payload.model_json_schema())
    by_path = {field.path: field for field in fields}
    assert by_path["tags"].value_kind == "enum"
    assert by_path["tags"].enum_values == ["vip", "b2b"]
    assert "contains" in by_path["tags"].ops
    assert by_path["scores"].value_kind == "integer"
    assert "contains" in by_path["scores"].ops


def test_derive_max_depth_truncates() -> None:
    schema: JsonObject = {
        "type": "object",
        "properties": {
            "l1": {
                "type": "object",
                "properties": {
                    "l2": {
                        "type": "object",
                        "properties": {
                            "l3": {
                                "type": "object",
                                "properties": {
                                    "l4": {
                                        "type": "object",
                                        "properties": {
                                            "l5": {
                                                "type": "object",
                                                "properties": {
                                                    "l6": {
                                                        "type": "object",
                                                        "properties": {
                                                            "l7": {
                                                                "type": "object",
                                                                "properties": {
                                                                    "too_deep": {
                                                                        "type": "string"
                                                                    }
                                                                },
                                                            }
                                                        },
                                                    }
                                                },
                                            }
                                        },
                                    }
                                },
                            }
                        },
                    }
                },
            }
        },
    }
    fields = derive_filter_fields(schema)
    paths = {field.path for field in fields}
    assert "l1.l2.l3.l4.l5.l6.l7.too_deep" not in paths


def test_derive_unknown_and_cyclic_ref_skipped() -> None:
    broken: JsonObject = {
        "type": "object",
        "properties": {"x": {"$ref": "#/$defs/Missing"}},
        "$defs": {},
    }
    assert derive_filter_fields(broken) == []

    cyclic: JsonObject = {
        "type": "object",
        "properties": {"node": {"$ref": "#/$defs/Node"}},
        "$defs": {
            "Node": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "child": {"$ref": "#/$defs/Node"},
                },
            }
        },
    }
    fields = derive_filter_fields(cyclic)
    paths = {field.path for field in fields}
    assert "node.label" in paths
    assert "node.child" not in paths or "node.child.label" not in paths


def test_derive_type_list_nullable_string() -> None:
    schema: JsonObject = {
        "type": "object",
        "properties": {
            "name": {"type": ["string", "null"]},
        },
    }
    fields = derive_filter_fields(schema)
    assert len(fields) == 1
    assert fields[0].path == "name"
    assert fields[0].value_kind == "string"


def test_derive_plain_oneof_without_discriminator() -> None:
    schema: JsonObject = {
        "type": "object",
        "properties": {
            "value": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {"alpha": {"type": "string"}},
                    },
                    {
                        "type": "object",
                        "properties": {"beta": {"type": "integer"}},
                    },
                ]
            }
        },
    }
    fields = derive_filter_fields(schema)
    paths = {field.path for field in fields}
    assert "value.alpha" in paths
    assert "value.beta" in paths
