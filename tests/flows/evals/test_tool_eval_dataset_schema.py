"""Validate tool contract eval dataset JSON structure (no live LLM)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter

from core.models import StrictBaseModel
from core.types import JsonObject

EVAL_DATASET_PATH = Path(__file__).with_name("tool_selection_cases.json")

EvalCaseKind = Literal["correct_tool_choice", "refuse_tool", "invalid_args"]
EvalExpectedAction = Literal["call_tool", "refuse_tool", "validation_error"]


class ToolEvalExpected(StrictBaseModel):
    action: EvalExpectedAction
    tool_name: str | None = None
    forbidden_tools: list[str] = Field(default_factory=list)


class ToolEvalToolCall(StrictBaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: JsonObject


class ToolEvalCase(StrictBaseModel):
    case_id: str = Field(..., min_length=1)
    kind: EvalCaseKind
    user_message: str = Field(..., min_length=1)
    available_tools: list[str] = Field(..., min_length=1)
    tool_call: ToolEvalToolCall | None = None
    expected: ToolEvalExpected


class ToolEvalDataset(StrictBaseModel):
    dataset_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    cases: list[ToolEvalCase] = Field(..., min_length=1)


def test_tool_selection_cases_schema() -> None:
    dataset = TypeAdapter(ToolEvalDataset).validate_json(
        EVAL_DATASET_PATH.read_text(encoding="utf-8")
    )
    assert dataset.dataset_id == "tool_contract_evals_v0"
    kinds = {case.kind for case in dataset.cases}
    assert "correct_tool_choice" in kinds
    assert "refuse_tool" in kinds
    assert "invalid_args" in kinds

    for case in dataset.cases:
        assert case.available_tools
        if case.kind == "correct_tool_choice":
            assert case.expected.action == "call_tool"
            assert case.expected.tool_name is not None
            assert case.expected.tool_name in case.available_tools
        elif case.kind == "refuse_tool":
            assert case.expected.action == "refuse_tool"
            assert case.expected.forbidden_tools
        elif case.kind == "invalid_args":
            assert case.expected.action == "validation_error"
            assert case.tool_call is not None
            assert case.tool_call.tool_name in case.available_tools
        else:
            raise AssertionError(f"unexpected case kind: {case.kind!r}")
