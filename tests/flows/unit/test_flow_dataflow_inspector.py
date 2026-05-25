from pydantic import TypeAdapter

from apps.flows.src.models import Edge, FlowVariableConfig, GraphNodeConfig
from apps.flows.src.services.flow_dataflow_inspector import inspect_flow_dataflow

_GRAPH_NODES_ADAPTER: TypeAdapter[dict[str, GraphNodeConfig]] = TypeAdapter(dict[str, GraphNodeConfig])


def _nodes(payload: dict[str, object]) -> dict[str, GraphNodeConfig]:
    return _GRAPH_NODES_ADAPTER.validate_python(payload)


def _edges(payload: list[dict[str, object]]) -> list[Edge]:
    return [Edge.model_validate(item) for item in payload]


def _variables(payload: dict[str, object]) -> dict[str, FlowVariableConfig]:
    return {key: FlowVariableConfig.model_validate(value) for key, value in payload.items()}


def test_inspector_propagates_code_return_and_output_mapping():
    result = inspect_flow_dataflow(
        flow_id="flow_1",
        branch_id="default",
        entry="code_1",
        variables=_variables({"api_key": {"value": "secret", "secret": True}}),
        sample_state={"content": "hello"},
        nodes=_nodes({
            "code_1": {
                "type": "code",
                "language": "python",
                "code": """
async def run(args, state):
    state.direct_value = "x"
    return {"answer": 42}
""",
                "output_mapping": {"answer": "mapped_answer"},
            },
            "llm_1": {
                "type": "llm_node",
                "input_mapping": {"prompt_answer": "@state:mapped_answer"},
            },
        }),
        edges=_edges([{"from_node": "code_1", "to_node": "llm_1"}]),
    )

    code_writes = {item.path for item in result.nodes["code_1"].writes}
    assert "direct_value" in code_writes
    assert "mapped_answer" in code_writes

    llm_inputs = result.nodes["llm_1"].input_mapping
    assert llm_inputs[0].status == "ok"
    assert llm_inputs[0].source_path == "mapped_answer"
    assert "code_1" in llm_inputs[0].producers


def test_inspector_reports_missing_input_mapping_path():
    result = inspect_flow_dataflow(
        flow_id="flow_1",
        branch_id="default",
        entry="llm_1",
        variables={},
        nodes=_nodes({
            "llm_1": {
                "type": "llm_node",
                "input_mapping": {"question": "@state:not_produced"},
            },
        }),
        edges=[],
    )

    node = result.nodes["llm_1"]
    assert node.input_mapping[0].status == "missing"
    assert any(issue.code == "missing_state_path" for issue in node.issues)


def test_inspector_reports_nested_output_mapping_runtime_warning():
    result = inspect_flow_dataflow(
        flow_id="flow_1",
        branch_id="default",
        entry="api_1",
        variables={},
        nodes=_nodes({
            "api_1": {
                "type": "external_api",
                "url": "https://example.test",
                "method": "GET",
                "state_mapping": {"name": "customer.name"},
            },
        }),
        edges=[],
    )

    node = result.nodes["api_1"]
    assert "customer.name" in {item.path for item in node.writes}
    assert any(issue.code == "nested_mapping_path_runtime" for issue in node.issues)


def test_inspector_merges_observed_run_diff_and_llm_tool_writes():
    result = inspect_flow_dataflow(
        flow_id="flow_1",
        branch_id="default",
        entry="llm_1",
        variables={},
        observed_runs={
            "llm_1": {
                "diff": [
                    {"path": "observed_answer", "old_value": None, "new_value": "ok", "change_type": "added"}
                ],
                "output_state": {"result": {"observed_answer": "ok"}},
                "observed_at": "2026-05-17T00:00:00Z",
            }
        },
        nodes=_nodes({
            "llm_1": {
                "type": "llm_node",
                "tools": [
                    {
                        "tool_id": "code_tool",
                        "type": "code",
                        "language": "python",
                        "code": "async def run(args, state):\n    state.tool_value = 1\n    return {'ok': True}",
                    }
                ],
            },
        }),
        edges=[],
    )

    node = result.nodes["llm_1"]
    writes_by_path = {item.path: item for item in node.writes}
    assert writes_by_path["observed_answer"].confidence == "observed"
    assert writes_by_path["tool_value"].confidence == "inferred_code"
    assert "observed_answer" in node.result_keys
