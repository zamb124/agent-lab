"""Фикстуры графов для тестов dataflow inspector."""

from __future__ import annotations

from typing import Any, cast

from pydantic import TypeAdapter

from apps.flows.src.models import Edge, FlowVariableConfig, GraphNodeConfig, TriggerConfig
from apps.flows.src.models.enums import NodeType
from apps.flows.src.services.flow_dataflow_inspector import inspect_flow_dataflow
from core.flow_ui.document import FlowUIDocument
from core.types import JsonObject

_GRAPH_NODES_ADAPTER: TypeAdapter[dict[str, GraphNodeConfig]] = TypeAdapter(
    dict[str, GraphNodeConfig]
)


def nodes(payload: dict[str, object]) -> dict[str, GraphNodeConfig]:
    return _GRAPH_NODES_ADAPTER.validate_python(payload)


def edges(payload: list[dict[str, object]]) -> list[Edge]:
    return [Edge.model_validate(item) for item in payload]


def variables(payload: dict[str, object]) -> dict[str, FlowVariableConfig]:
    return {key: FlowVariableConfig.model_validate(value) for key, value in payload.items()}


def node_of(node_type: NodeType | str, node_id: str = "n1", **kwargs: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": str(node_type.value if isinstance(node_type, NodeType) else node_type)
    }
    base.update(kwargs)
    return {node_id: base}


def chain(
    *node_ids: str, node_type: str = "llm_node"
) -> tuple[dict[str, object], list[dict[str, object]]]:
    nodes_payload: dict[str, object] = {}
    edges_payload: list[dict[str, object]] = []
    for nid in node_ids:
        nodes_payload[nid] = (
            {"type": node_type, "prompt": "ok"} if node_type == "llm_node" else {"type": node_type}
        )
    for idx in range(len(node_ids) - 1):
        edges_payload.append({"from_node": node_ids[idx], "to_node": node_ids[idx + 1]})
    return nodes_payload, edges_payload


def diamond() -> tuple[dict[str, object], list[dict[str, object]]]:
    return (
        {
            "a": {"type": "code", "language": "python", "code": "async def run(a,s): return {}"},
            "b": {"type": "llm_node", "prompt": "{x}"},
            "c": {"type": "llm_node", "prompt": "{y}"},
            "d": {"type": "llm_node", "prompt": "{z}"},
        },
        [
            {"from_node": "a", "to_node": "b"},
            {"from_node": "a", "to_node": "c"},
            {"from_node": "b", "to_node": "d"},
            {"from_node": "c", "to_node": "d"},
        ],
    )


def triggers(payload: dict[str, object]) -> dict[str, TriggerConfig]:
    return {key: TriggerConfig.model_validate(value) for key, value in payload.items()}


def inspect(
    *,
    flow_id: str = "flow_test",
    branch_id: str = "default",
    entry: str | None = "n1",
    nodes_payload: dict[str, object] | None = None,
    edges_payload: list[dict[str, object]] | None = None,
    variables_payload: dict[str, object] | None = None,
    triggers_payload: dict[str, object] | None = None,
    sample_state: dict[str, object] | None = None,
    observed_runs: dict[str, object] | None = None,
    interface: FlowUIDocument | None = None,
):
    return inspect_flow_dataflow(
        flow_id=flow_id,
        branch_id=branch_id,
        entry=entry,
        variables=variables(variables_payload or {}),
        triggers=triggers(triggers_payload or {}),
        sample_state=cast(JsonObject | None, sample_state),
        observed_runs=cast(JsonObject, observed_runs or {}),
        nodes=nodes(nodes_payload or {"n1": {"type": "llm_node", "prompt": "hi"}}),
        edges=edges(edges_payload or []),
        interface=interface,
    )


def issue_assert(
    node_info: Any,
    code: str,
    *,
    target: str | None = None,
    path: str | None = None,
    severity: str | None = None,
) -> None:
    matched = [
        issue
        for issue in node_info.issues
        if issue.code == code
        and (target is None or issue.target == target)
        and (path is None or issue.path == path)
    ]
    assert matched, (
        f"Expected issue {code!r} target={target!r} path={path!r}, got {[i.code for i in node_info.issues]}"
    )
    if severity is not None:
        assert matched[0].severity == severity


def graph_issue_assert(result: Any, code: str) -> None:
    matched = [issue for issue in result.issues if issue.code == code]
    assert matched, f"Expected graph issue {code!r}, got {[i.code for i in result.issues]}"


MINIMAL_NODE_CONFIGS: dict[str, dict[str, object]] = {
    NodeType.LLM_NODE.value: {"type": "llm_node", "prompt": "Hello"},
    NodeType.CODE.value: {
        "type": "code",
        "language": "python",
        "code": "async def run(args, state):\n    return {}",
    },
    NodeType.FLOW.value: {"type": "flow", "flow_id": "nested_flow"},
    NodeType.REMOTE_FLOW.value: {
        "type": "remote_flow",
        "url": "https://example.test/a2a",
        "branch_id": "default",
    },
    NodeType.CODE_AGENT.value: {
        "type": "code_agent",
        "language": "python",
        "invoke_kind": "cli",
        "catalog_id": "cat_code_agent",
        "invoke_argv": ["python", "main.py"],
    },
    NodeType.EXTERNAL_API.value: {
        "type": "external_api",
        "url": "https://example.test",
        "method": "GET",
    },
    NodeType.MCP.value: {"type": "mcp", "server_id": "srv", "tool_name": "tool"},
    NodeType.DATASOURCE.value: {
        "type": "datasource",
        "connector_id": "postgres",
        "datasource_id": "ds1",
        "datasource_operation": "query",
        "sql": "SELECT 1",
    },
    NodeType.CHANNEL.value: {"type": "channel", "channel": "telegram", "action": "send"},
    NodeType.HITL_NODE.value: {"type": "hitl_node", "work_queue_slug": "ops"},
    NodeType.REFLECTION.value: {
        "type": "reflection",
        "llm": {"model": "mock-gpt-4", "temperature": 0.0},
        "critic_policy": {
            "policy_id": "final-answer-safety",
            "gate": "final_answer",
            "target": {"kind": "response"},
            "instruction": "Block unsafe final answers.",
            "criteria": [
                {
                    "criterion_id": "safety",
                    "description": "No destructive instructions.",
                    "severity": "critical",
                }
            ],
            "min_confidence": 0.8,
            "block_on_severities": ["error", "critical"],
        },
    },
    NodeType.RESOURCE.value: {"type": "resource"},
}
