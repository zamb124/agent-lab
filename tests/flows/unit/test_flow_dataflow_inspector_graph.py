"""Graph propagation, node types и canvas summary."""

import pytest

from apps.flows.src.models.enums import NodeType
from tests.flows.fixtures.dataflow_graphs import (
    MINIMAL_NODE_CONFIGS,
    diamond,
    inspect,
    issue_assert,
)


@pytest.mark.parametrize("node_type", [member.value for member in NodeType])
def test_inspector_smoke_all_node_types(node_type: str):
    config = MINIMAL_NODE_CONFIGS.get(node_type, {"type": node_type})
    result = inspect(
        entry="n1",
        nodes_payload={"n1": config},
        edges_payload=[{"from_node": "n1", "to_node": None}],
    )
    node = result.nodes["n1"]
    assert node.canvas is not None
    assert isinstance(node.issues, list)
    assert isinstance(node.input_mapping, list)
    assert isinstance(node.required_inputs, list)


def test_inspector_multi_hop_producer_on_target():
    result = inspect(
        entry="a",
        nodes_payload={
            "a": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    state.topic='x'\n    return {}",
            },
            "b": {"type": "code", "language": "python", "code": "async def run(a,s):\n    return {}"},
            "c": {"type": "llm_node", "prompt": "{topic}", "input_mapping": {"topic": "@state:topic"}},
        },
        edges_payload=[
            {"from_node": "a", "to_node": "b"},
            {"from_node": "b", "to_node": "c"},
        ],
    )
    row = result.nodes["c"].input_mapping[0]
    assert row.status == "ok"
    assert "a" in row.producers


def test_inspector_diamond_merge_descriptors():
    nodes_payload, edges_payload = diamond()
    result = inspect(
        entry="a",
        nodes_payload={
            **nodes_payload,
            "a": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    state.x=1\n    state.y=2\n    return {}",
            },
        },
        edges_payload=edges_payload,
    )
    assert result.nodes["d"].incoming_state


def test_inspector_conditional_edge_marks_maybe_availability():
    result = inspect(
        entry="a",
        nodes_payload={
            "a": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    state.flag=True\n    return {}",
            },
            "b": {"type": "llm_node", "prompt": "ok"},
        },
        edges_payload=[
            {
                "from_node": "a",
                "to_node": "b",
                "condition": {"type": "simple", "variable": "flag", "operator": "==", "value": True},
            },
        ],
    )
    incoming = {item.path: item for item in result.nodes["b"].incoming_state}
    if "flag" in incoming:
        assert incoming["flag"].availability == "maybe"


def test_inspector_non_join_edge_marks_non_join_contribution():
    result = inspect(
        entry="a",
        nodes_payload={
            "a": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    state.x=1\n    return {}",
            },
            "b": {"type": "llm_node", "prompt": "ok"},
        },
        edges_payload=[{"from_node": "a", "to_node": "b", "contributes_to_join": False}],
    )
    incoming = {item.path: item for item in result.nodes["b"].incoming_state}
    if "x" in incoming:
        assert incoming["x"].join_contribution == "non_join"


def test_inspector_secret_variable_masking():
    result = inspect(
        entry="llm_1",
        nodes_payload={
            "llm_1": {"type": "llm_node", "input_mapping": {"token": "@var:api_key"}},
        },
        variables_payload={"api_key": {"value": "secret", "secret": True}},
    )
    row = result.nodes["llm_1"].input_mapping[0]
    assert row.status == "ok"
    assert row.sample_value == "<secret>"


def test_inspector_sample_state_bootstraps_entry():
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "input_mapping": {"content": "@state:content"}}},
        sample_state={"content": "hello"},
    )
    row = result.nodes["llm_1"].input_mapping[0]
    assert row.status == "ok"


def test_inspector_observed_run_removed_diff():
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "prompt": "ok"}},
        observed_runs={
            "llm_1": {
                "diff": [{"path": "temp", "old_value": "x", "new_value": None, "change_type": "removed"}],
            },
        },
    )
    writes = {item.path: item for item in result.nodes["llm_1"].writes}
    assert "temp" in writes


def test_inspector_canvas_summary_counts_and_producers():
    result = inspect(
        entry="code_1",
        nodes_payload={
            "code_1": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    state.topic='x'\n    return {}",
            },
            "llm_1": {
                "type": "llm_node",
                "prompt": "{topic}",
                "input_mapping": {"topic": "@state:topic"},
                "input_schema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                    "required": ["limit"],
                },
            },
        },
        edges_payload=[{"from_node": "code_1", "to_node": "llm_1"}],
    )
    canvas = result.nodes["llm_1"].canvas
    assert canvas.has_issues is True
    assert canvas.error_count >= 1
    assert any(chip.producer_node == "code_1" for chip in canvas.inputs if chip.label == "topic")
    issue_assert(result.nodes["llm_1"], "missing_required_input", target="limit")


def test_inspector_llm_structured_output_declares_schema_keys():
    result = inspect(
        entry="llm_1",
        nodes_payload={
            "llm_1": {
                "type": "llm_node",
                "prompt": "ok",
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {"answer": {"type": "string"}},
                },
            },
        },
    )
    writes = {item.path for item in result.nodes["llm_1"].writes}
    assert "answer" in writes


def test_inspector_local_variables_satisfy_prompt():
    result = inspect(
        entry="llm_1",
        nodes_payload={
            "llm_1": {
                "type": "llm_node",
                "prompt": "{topic}",
                "local_variables": {"topic": "preset"},
            },
        },
    )
    req = result.nodes["llm_1"].required_inputs[0]
    assert req.name == "topic"
    assert req.satisfied is True


def test_inspector_entry_canvas_excludes_runtime_sample_state_noise():
    result = inspect(
        entry="code_1",
        nodes_payload={"code_1": {"type": "code", "language": "python", "code": "async def run(a,s): return {}"}},
        variables_payload={"alpha": {"value": "a"}, "beta": {"value": "b"}},
        sample_state={
            "content": "hello",
            "breakpoint_state": {"hit": True},
            "node_history": ["code_1"],
            "variables": {
                "alpha": "a",
                "beta": "b",
                "nested": {"deep": "x"},
            },
        },
    )
    labels = {chip.label for chip in result.nodes["code_1"].canvas.inputs}
    assert "content" in labels
    assert "variables.alpha" in labels
    assert "variables.beta" in labels
    assert "breakpoint_state" not in labels
    assert "node_history" not in labels
    assert "variables.nested" not in labels
    assert "variables.nested.deep" not in labels


def test_inspector_entry_canvas_includes_flow_variables_without_triggers():
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "prompt": "ok"}},
        variables_payload={"company_name": {"value": "ACME"}, "limit": {"value": 10}},
    )
    labels = {chip.label for chip in result.nodes["llm_1"].canvas.inputs}
    assert labels == {"content", "variables.company_name", "variables.limit"}


def test_inspector_entry_canvas_includes_trigger_mapping_paths():
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "prompt": "ok"}},
        triggers_payload={
            "tg_1": {
                "trigger_id": "tg_1",
                "name": "Telegram",
                "type": "telegram",
                "enabled": True,
                "output_mapping": {
                    "content": "message.text",
                    "context.chat_id": "message.chat.id",
                },
            },
        },
    )
    labels = {chip.label for chip in result.nodes["llm_1"].canvas.inputs}
    assert "content" in labels
    assert "triggers.tg_1.context.chat_id" in labels
    assert "triggers.tg_1.payload" in labels


def test_inspector_downstream_without_contract_has_empty_canvas_inputs():
    result = inspect(
        entry="code_1",
        nodes_payload={
            "code_1": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    state.topic='x'\n    return {}",
            },
            "llm_1": {"type": "llm_node", "prompt": "ok"},
        },
        edges_payload=[{"from_node": "code_1", "to_node": "llm_1"}],
        sample_state={"topic": "x", "breakpoint_state": {"hit": True}},
    )
    assert result.nodes["llm_1"].canvas.inputs == []


def test_inspector_downstream_canvas_only_explicit_contract():
    result = inspect(
        entry="code_1",
        nodes_payload={
            "code_1": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    state.topic='x'\n    return {}",
            },
            "llm_1": {
                "type": "llm_node",
                "prompt": "{topic}",
                "input_mapping": {"topic": "@state:topic"},
            },
        },
        edges_payload=[{"from_node": "code_1", "to_node": "llm_1"}],
    )
    labels = {chip.label for chip in result.nodes["llm_1"].canvas.inputs}
    assert labels == {"topic"}


def test_inspector_code_reads_link_mcp_output_to_downstream_emit():
    """public_search: search_result_insights (mcp) -> emit_search_insights (code)."""
    result = inspect(
        entry="search_result_insights",
        nodes_payload={
            "search_result_insights": {
                "type": "mcp",
                "server_id": "search",
                "tool_name": "search_result_insights",
                "output_mapping": {"insights": "search_result_insights"},
            },
            "emit_search_insights": {
                "type": "code",
                "language": "python",
                "code": (
                    "async def run(args, state):\n"
                    "    payload = {'result_insights': state['search_result_insights']}\n"
                    "    return {}\n"
                ),
            },
        },
        edges_payload=[
            {"from_node": "search_result_insights", "to_node": "emit_search_insights"},
        ],
    )
    emit = result.nodes["emit_search_insights"]
    read_paths = {row.source_path for row in emit.reads}
    assert "search_result_insights" in read_paths

    incoming = {desc.path: desc for desc in emit.incoming_state}
    assert "search_result_insights" in incoming
    assert "search_result_insights" in incoming["search_result_insights"].producers

    canvas_labels = {chip.label for chip in emit.canvas.inputs}
    assert "search_result_insights" in canvas_labels
    insight_chip = next(chip for chip in emit.canvas.inputs if chip.label == "search_result_insights")
    assert insight_chip.producer_node == "search_result_insights"

    mcp_writes = {desc.path for desc in result.nodes["search_result_insights"].writes}
    assert "search_result_insights" in mcp_writes


def test_inspector_optional_state_get_read_not_marked_missing():
    """build_search_artifact: state.get('search_results_refined') is optional fallback."""
    result = inspect(
        entry="answer",
        nodes_payload={
            "answer": {
                "type": "code",
                "language": "python",
                "code": (
                    "def _require_list(state, key):\n"
                    "    return state[key]\n"
                    "\n"
                    "async def run(args, state):\n"
                    "    refined = state.get('search_results_refined')\n"
                    "    if isinstance(refined, list) and refined:\n"
                    "        results = refined\n"
                    "    else:\n"
                    "        results = _require_list(state, 'search_results')\n"
                    "    return {'response': results}\n"
                ),
            },
        },
        edges_payload=[],
        sample_state={"search_results": []},
    )
    artifact = result.nodes["answer"]
    refined_read = next(row for row in artifact.reads if row.source_path == "search_results_refined")
    assert refined_read.status == "ok"
    assert not any(
        issue.code == "missing_state_path" and issue.path == "search_results_refined"
        for issue in artifact.issues
    )
    refined_chip = next(chip for chip in artifact.canvas.inputs if chip.label == "search_results_refined")
    assert refined_chip.status == "ok"
