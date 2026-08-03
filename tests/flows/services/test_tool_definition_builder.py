"""Tests for build_tool_definition_from_base_tool."""

from __future__ import annotations

import pytest

from apps.flows.src.services.tool_definition_builder import build_tool_definition_from_base_tool
from apps.flows.src.tools.base import BaseTool
from core.state import ExecutionState
from core.types import JsonObject, JsonValue


class _SampleWriteTool(BaseTool):
    name = "sample_write"
    description = "Writes a sample entity."
    effects = ["create"]
    confirmation_floor = "preview"
    idempotency = "supported"
    argument_sources = {"title": "model"}
    output_schema: JsonObject | None = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "additionalProperties": False,
        "required": ["ok"],
    }

    @property
    def parameters(self) -> JsonObject:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        }

    async def _run_impl(self, args: JsonObject, state: ExecutionState) -> JsonValue:
        _ = args
        _ = state
        return {"ok": True}


class _BadEffectTool(BaseTool):
    name = "bad_effect"
    description = "Has an invalid effect."
    effects = ["explode"]

    async def _run_impl(self, args: JsonObject, state: ExecutionState) -> JsonValue:
        _ = args
        _ = state
        return {}


def test_build_tool_definition_from_base_tool() -> None:
    definition = build_tool_definition_from_base_tool(_SampleWriteTool())
    assert definition.definition_id == "sample_write"
    assert definition.machine_name == "sample_write"
    assert definition.effects == ["create"]
    assert definition.confirmation_floor == "preview"
    assert definition.idempotency == "supported"
    assert definition.executor_kind == "trusted_builtin"
    assert definition.argument_sources["title"] == "model"
    assert definition.canonical_output_schema["required"] == ["ok"]


def test_build_tool_definition_rejects_unknown_effect() -> None:
    with pytest.raises(ValueError, match="unknown effect"):
        build_tool_definition_from_base_tool(_BadEffectTool())
