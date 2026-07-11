"""Property-based fuzz tests for flow dataflow inspector."""

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.flows.src.models import DataflowInspectResult
from apps.flows.src.models.enums import NodeType
from tests.flows.fixtures.dataflow_graphs import inspect

_NODE_TYPES = [member.value for member in NodeType]
_NODE_ID = st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True)


def _minimal_node(node_type: str) -> dict[str, object]:
    if node_type == "llm_node":
        return {"type": node_type, "prompt": "ok"}
    if node_type == "code":
        return {"type": node_type, "language": "python", "code": "async def run(a,s): return {}"}
    if node_type == "external_api":
        return {"type": node_type, "url": "https://example.test", "method": "GET"}
    if node_type == "channel":
        return {"type": node_type, "channel": "telegram", "action": "send"}
    if node_type == "hitl_node":
        return {"type": node_type, "work_queue_slug": "ops"}
    if node_type == "reflection":
        return {
            "type": node_type,
            "llm": {"model": "mock-gpt-4", "temperature": 0.0},
            "critic_policy": {
                "policy_id": "fuzz-policy",
                "gate": "final_answer",
                "target": {"kind": "response"},
                "instruction": "Check response.",
                "criteria": [
                    {
                        "criterion_id": "ok",
                        "description": "Must be safe.",
                        "severity": "error",
                    }
                ],
                "min_confidence": 0.5,
                "block_on_severities": ["error", "critical"],
            },
        }
    if node_type in {"flow", "remote_flow"}:
        return {"type": node_type, "flow_id": "nested"}
    if node_type == "mcp":
        return {"type": node_type, "server_id": "srv", "tool_name": "tool"}
    return {"type": node_type}


@settings(max_examples=120, deadline=None)
@given(
    st.dictionaries(_NODE_ID, st.sampled_from(_NODE_TYPES), min_size=1, max_size=6),
    st.data(),
)
def test_inspect_never_crashes_on_random_graph(node_types: dict[str, str], data: st.DataObject) -> None:
    node_ids = list(node_types.keys())
    edge_pairs = data.draw(
        st.lists(
            st.tuples(st.sampled_from(node_ids), st.sampled_from(node_ids)),
            min_size=0,
            max_size=min(8, len(node_ids) * 2),
        )
    )
    nodes_payload = {nid: _minimal_node(ntype) for nid, ntype in node_types.items()}
    edges_payload = [{"from_node": src, "to_node": dst} for src, dst in edge_pairs if src != dst]
    entry = node_ids[0]
    result = inspect(
        entry=entry,
        nodes_payload=nodes_payload,
        edges_payload=edges_payload,
    )
    assert isinstance(result, DataflowInspectResult)
    for node_id in node_ids:
        assert node_id in result.nodes
        info = result.nodes[node_id]
        assert info.canvas is not None
        assert isinstance(info.issues, list)
        assert isinstance(info.input_mapping, list)


@settings(max_examples=80, deadline=None)
@given(
    st.dictionaries(_NODE_ID, st.just("llm_node"), min_size=1, max_size=4),
    st.text(max_size=120),
)
def test_inspect_llm_prompt_templates(node_ids: dict[str, str], prompt_suffix: str) -> None:
    nodes_payload = {nid: {"type": "llm_node", "prompt": f"{{topic}} {prompt_suffix}"} for nid in node_ids}
    result = inspect(entry=list(node_ids)[0], nodes_payload=nodes_payload, edges_payload=[])
    for info in result.nodes.values():
        assert info.canvas.error_count + info.canvas.warning_count >= 0
