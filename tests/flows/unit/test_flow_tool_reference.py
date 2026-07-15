from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models import FlowToolReference, GraphNodeConfig, NodeConfig
from apps.flows.src.models.enums import NodeToolCallType, NodeType

pytestmark = [pytest.mark.no_test_doubles]


def test_flow_tool_reference_materializes_complete_default_contract() -> None:
    ref = FlowToolReference(tool_id="coach", flow_id="coach")

    assert ref.type == NodeType.FLOW
    assert ref.branch_id == "default"
    assert ref.call_type == NodeToolCallType.CALL
    assert ref.name == "coach"
    assert ref.parameters_schema == {
        "type": "object",
        "properties": {
            "request": {
                "type": "string",
                "description": "Запрос, передаваемый дочернему flow",
            }
        },
        "required": ["request"],
        "additionalProperties": False,
    }


@pytest.mark.parametrize("call_type", ["transfer", "delegate", "", True])
def test_flow_tool_reference_rejects_unknown_call_type(call_type: object) -> None:
    with pytest.raises(ValidationError):
        FlowToolReference.model_validate(
            {
                "tool_id": "coach",
                "type": "flow",
                "flow_id": "coach",
                "call_type": call_type,
            }
        )


@pytest.mark.parametrize("missing_field", ["tool_id", "flow_id"])
def test_flow_tool_reference_requires_both_identifiers(missing_field: str) -> None:
    payload = {
        "tool_id": "coach",
        "type": "flow",
        "flow_id": "coach",
        "call_type": "handoff",
    }
    del payload[missing_field]

    with pytest.raises(ValidationError):
        FlowToolReference.model_validate(payload)


def test_graph_node_accepts_handoff_only_on_specific_flow_tool() -> None:
    graph_node = GraphNodeConfig.model_validate(
        {
            "type": "llm_node",
            "tools": [
                {
                    "tool_id": "coach",
                    "type": "flow",
                    "flow_id": "coach",
                    "branch_id": "vip",
                    "call_type": "handoff",
                }
            ],
        }
    )

    tool = graph_node.tools[0]
    assert isinstance(tool, FlowToolReference)
    assert tool.call_type == NodeToolCallType.HANDOFF
    assert tool.branch_id == "vip"


def test_graph_llm_node_rejects_root_call_type() -> None:
    with pytest.raises(ValidationError, match="call_type is only allowed on flow nodes"):
        GraphNodeConfig.model_validate(
            {
                "type": "llm_node",
                "call_type": "handoff",
                "tools": [],
            }
        )


def test_graph_flow_node_rejects_hitl_handoff_mode_boolean() -> None:
    with pytest.raises(ValidationError):
        GraphNodeConfig.model_validate(
            {
                "type": "flow",
                "flow_id": "coach",
                "handoff_mode": True,
            }
        )


def test_node_as_tool_rejects_handoff_for_non_flow_node() -> None:
    with pytest.raises(ValidationError, match="only allowed for flow node-as-tool"):
        NodeConfig.model_validate(
            {
                "node_id": "nested_llm",
                "type": "llm_node",
                "call_type": "handoff",
            }
        )
