"""Валидация Edge.from_port и coverage выходов reflection."""

from __future__ import annotations

import pytest

from apps.flows.src.services.flow_validator import FlowValidator, ValidationSeverity
from core.reflection import CriticExit, CriticExitWhen
from core.types import JsonObject
from tests.flows.fixtures.reflection import reflection_policy


def _three_exit_policy() -> JsonObject:
    policy = reflection_policy()
    return policy.model_copy(
        update={
            "exits": [
                CriticExit(
                    exit_id="pass",
                    label="Pass",
                    when=CriticExitWhen(kind="approved_true"),
                ),
                CriticExit(
                    exit_id="revise",
                    label="Revise",
                    when=CriticExitWhen(kind="decision_eq", decision="needs_revision"),
                ),
                CriticExit(
                    exit_id="reject",
                    label="Reject",
                    when=CriticExitWhen(kind="always"),
                ),
            ]
        }
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_reflection_from_port_unknown_is_error() -> None:
    validator = FlowValidator()
    nodes: dict[str, JsonObject] = {
        "entry": {"type": "llm_node", "name": "entry"},
        "critic": {"type": "reflection", "name": "critic"},
    }
    edges: list[JsonObject] = [
        {"from_node": "entry", "to_node": "critic"},
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "maybe",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "maybe",
            },
        },
    ]
    result = await validator.validate(nodes=nodes, edges=edges, entry="entry", variables={}, flow_id="f1")
    codes = {err.code for err in result.errors}
    assert "edge_from_port_unknown" in codes


@pytest.mark.asyncio
async def test_reflection_exits_incomplete_is_error() -> None:
    validator = FlowValidator()
    nodes: dict[str, JsonObject] = {
        "entry": {"type": "llm_node", "name": "entry"},
        "critic": {"type": "reflection", "name": "critic"},
    }
    edges: list[JsonObject] = [
        {"from_node": "entry", "to_node": "critic"},
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "approved",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "approved",
            },
        },
    ]
    result = await validator.validate(nodes=nodes, edges=edges, entry="entry", variables={}, flow_id="f1")
    incomplete = [err for err in result.errors if err.code == "reflection_exits_incomplete"]
    assert len(incomplete) == 1
    assert incomplete[0].severity is ValidationSeverity.ERROR
    assert incomplete[0].details is not None
    assert incomplete[0].details["missing_ports"] == ["blocked"]
    assert result.valid is False


@pytest.mark.asyncio
async def test_reflection_both_exits_ok() -> None:
    validator = FlowValidator()
    nodes: dict[str, JsonObject] = {
        "entry": {"type": "llm_node", "name": "entry"},
        "critic": {"type": "reflection", "name": "critic"},
    }
    edges: list[JsonObject] = [
        {"from_node": "entry", "to_node": "critic"},
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "approved",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "approved",
            },
        },
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "blocked",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "blocked",
            },
        },
    ]
    result = await validator.validate(
        nodes=nodes, edges=edges, entry="entry", variables={}, flow_id="f1"
    )
    codes = {err.code for err in result.errors}
    assert "reflection_exits_incomplete" not in codes
    assert "edge_from_port_unknown" not in codes


@pytest.mark.asyncio
async def test_reflection_exits_covered_by_legacy_approved_condition() -> None:
    """Legacy validation.approved still covers default approved/blocked exits."""
    validator = FlowValidator()
    nodes: dict[str, JsonObject] = {
        "entry": {"type": "llm_node", "name": "entry"},
        "critic": {"type": "reflection", "name": "critic"},
    }
    edges: list[JsonObject] = [
        {"from_node": "entry", "to_node": "critic"},
        {
            "from_node": "critic",
            "to_node": None,
            "condition": {
                "type": "simple",
                "variable": "validation.approved",
                "operator": "==",
                "value": True,
            },
        },
        {
            "from_node": "critic",
            "to_node": None,
            "condition": {
                "type": "simple",
                "variable": "validation.approved",
                "operator": "==",
                "value": False,
            },
        },
    ]
    result = await validator.validate(
        nodes=nodes, edges=edges, entry="entry", variables={}, flow_id="f-infer"
    )
    codes = {err.code for err in result.errors}
    assert "reflection_exits_incomplete" not in codes


@pytest.mark.asyncio
async def test_reflection_three_exits_coverage() -> None:
    validator = FlowValidator()
    policy = _three_exit_policy()
    nodes: dict[str, JsonObject] = {
        "entry": {"type": "llm_node", "name": "entry"},
        "critic": {
            "type": "reflection",
            "name": "critic",
            "critic_policy": policy,
        },
    }
    edges: list[JsonObject] = [
        {"from_node": "entry", "to_node": "critic"},
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "pass",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "pass",
            },
        },
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "revise",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "revise",
            },
        },
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "reject",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "reject",
            },
        },
    ]
    result = await validator.validate(
        nodes=nodes, edges=edges, entry="entry", variables={}, flow_id="f3"
    )
    codes = {err.code for err in result.errors}
    assert "reflection_exits_incomplete" not in codes
    assert "edge_from_port_unknown" not in codes


@pytest.mark.asyncio
async def test_reflection_three_exits_incomplete() -> None:
    validator = FlowValidator()
    nodes: dict[str, JsonObject] = {
        "entry": {"type": "llm_node", "name": "entry"},
        "critic": {
            "type": "reflection",
            "name": "critic",
            "critic_policy": _three_exit_policy(),
        },
    }
    edges: list[JsonObject] = [
        {"from_node": "entry", "to_node": "critic"},
        {
            "from_node": "critic",
            "to_node": None,
            "from_port": "pass",
            "condition": {
                "type": "simple",
                "variable": "validation.exit_id",
                "operator": "==",
                "value": "pass",
            },
        },
    ]
    result = await validator.validate(
        nodes=nodes, edges=edges, entry="entry", variables={}, flow_id="f3-miss"
    )
    incomplete = [err for err in result.errors if err.code == "reflection_exits_incomplete"]
    assert len(incomplete) == 1
    assert incomplete[0].details is not None
    assert incomplete[0].details["missing_ports"] == ["reject", "revise"]
