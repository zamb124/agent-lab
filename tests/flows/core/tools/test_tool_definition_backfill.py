"""Parity tests: builtin BaseTool → ToolDefinition backfill."""

from __future__ import annotations

from apps.flows.src.models.tool_contracts import ToolDefinition
from apps.flows.src.services.tool_definition_backfill import (
    BUILTIN_TOOL_DEFINITION_SEMVER,
    BUILTIN_TOOL_DEFINITION_VERSION,
    iter_builtin_tool_definitions,
)
from apps.flows.tools.builtin_specs import BUILTIN_TOOL_SPECS


def test_iter_builtin_tool_definitions_count_matches_specs() -> None:
    definitions = iter_builtin_tool_definitions()
    assert len(definitions) == len(BUILTIN_TOOL_SPECS)


def test_all_builtins_produce_valid_tool_definition() -> None:
    definitions = iter_builtin_tool_definitions()
    assert definitions
    for definition in definitions:
        restored = ToolDefinition.model_validate(definition.model_dump(mode="json"))
        assert restored == definition
        assert restored.version == BUILTIN_TOOL_DEFINITION_VERSION
        assert restored.executor_kind == "trusted_builtin"
        assert restored.definition_id == restored.title
        assert restored.provenance == {
            "owner": "platform",
            "trust": "platform",
            "semver": BUILTIN_TOOL_DEFINITION_SEMVER,
        }


def test_each_builtin_canonical_input_schema_is_object() -> None:
    for definition in iter_builtin_tool_definitions():
        schema = definition.canonical_input_schema
        assert schema.get("type") == "object", definition.definition_id
        assert isinstance(schema.get("properties"), dict), definition.definition_id
