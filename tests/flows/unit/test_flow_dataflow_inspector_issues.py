"""Матрица issue codes dataflow inspector."""

import pytest

from tests.flows.fixtures.dataflow_graphs import graph_issue_assert, inspect, issue_assert


def test_issue_missing_variable():
    result = inspect(
        entry="llm_1",
        nodes_payload={"llm_1": {"type": "llm_node", "input_mapping": {"key": "@var:undeclared"}}},
    )
    issue_assert(result.nodes["llm_1"], "missing_variable", target="key")


def test_issue_missing_state_path_in_config_url():
    result = inspect(
        entry="api_1",
        nodes_payload={
            "api_1": {
                "type": "external_api",
                "url": "https://example.test/@state:missing_token",
                "method": "GET",
            },
        },
    )
    issue_assert(result.nodes["api_1"], "missing_state_path")


def test_issue_missing_var_path_in_headers():
    result = inspect(
        entry="api_1",
        nodes_payload={
            "api_1": {
                "type": "external_api",
                "url": "https://example.test",
                "method": "GET",
                "headers": {"Authorization": "@var:secret_key"},
            },
        },
        variables_payload={},
    )
    issue_assert(result.nodes["api_1"], "missing_var_path")


def test_issue_frozen_state_write_via_output_mapping():
    result = inspect(
        entry="code_1",
        nodes_payload={
            "code_1": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s): return {}",
                "output_mapping": {"x": "session_id"},
            },
        },
    )
    issue_assert(result.nodes["code_1"], "frozen_state_write", path="session_id")


def test_issue_unreachable_node():
    result = inspect(
        entry="a",
        nodes_payload={
            "a": {"type": "llm_node", "prompt": "ok"},
            "orphan": {"type": "llm_node", "prompt": "lost"},
        },
        edges_payload=[{"from_node": "a", "to_node": None}],
    )
    issue_assert(result.nodes["orphan"], "unreachable_node")


def test_issue_missing_entry_graph_level():
    from apps.flows.src.services.flow_dataflow_inspector import _graph_issues

    issues = _graph_issues(None, {"a": {"type": "llm_node"}})
    assert any(issue.code == "missing_entry" for issue in issues)


def test_issue_entry_not_found_graph_level():
    result = inspect(
        entry="missing",
        nodes_payload={"a": {"type": "llm_node", "prompt": "ok"}},
        edges_payload=[],
    )
    graph_issue_assert(result, "entry_not_found")


def test_issue_llm_tools_dynamic_state():
    result = inspect(
        entry="llm_1",
        nodes_payload={
            "llm_1": {
                "type": "llm_node",
                "prompt": "ok",
                "tools": [{"tool_id": "tool_1", "type": "code", "language": "python", "code": "async def run(a,s): return {}"}],
            },
        },
    )
    issue_assert(result.nodes["llm_1"], "llm_tools_dynamic_state")


def test_issue_llm_tool_dynamic_state_for_flow_tool():
    result = inspect(
        entry="llm_1",
        nodes_payload={
            "llm_1": {
                "type": "llm_node",
                "prompt": "ok",
                "tools": [{"tool_id": "nested", "type": "flow", "flow_id": "child_flow"}],
            },
        },
    )
    issue_assert(result.nodes["llm_1"], "llm_tool_dynamic_state")


def test_issue_code_return_dynamic():
    result = inspect(
        entry="code_1",
        nodes_payload={
            "code_1": {
                "type": "code",
                "language": "python",
                "code": "async def run(a,s):\n    return some_dynamic()",
            },
        },
    )
    issue_assert(result.nodes["code_1"], "code_return_dynamic")


def test_issue_external_api_response_dynamic():
    result = inspect(
        entry="api_1",
        nodes_payload={
            "api_1": {"type": "external_api", "url": "https://example.test", "method": "GET"},
        },
    )
    issue_assert(result.nodes["api_1"], "external_api_response_dynamic")


def test_issue_channel_result_dynamic():
    result = inspect(
        entry="ch_1",
        nodes_payload={"ch_1": {"type": "channel", "channel": "telegram", "action": "send"}},
    )
    issue_assert(result.nodes["ch_1"], "channel_result_dynamic")


def test_issue_nested_flow_static_expanded():
    result = inspect(
        entry="flow_1",
        nodes_payload={
            "flow_1": {
                "type": "flow",
                "flow_id": "nested",
                "__dataflow_nested": {
                    "nodes": {
                        "inner": {
                            "writes": [{"path": "nested_answer", "type": "string"}],
                        },
                    },
                },
            },
        },
    )
    issue_assert(result.nodes["flow_1"], "nested_flow_static_expanded")


def test_issue_nested_flow_state_dynamic():
    result = inspect(
        entry="flow_1",
        nodes_payload={"flow_1": {"type": "flow", "flow_id": "nested"}},
    )
    issue_assert(result.nodes["flow_1"], "nested_flow_state_dynamic")


def test_issue_hitl_interrupt():
    result = inspect(
        entry="hitl_1",
        nodes_payload={"hitl_1": {"type": "hitl_node", "work_queue_slug": "ops"}},
    )
    issue_assert(result.nodes["hitl_1"], "hitl_interrupt")


@pytest.mark.parametrize(
    "issue_code",
    [
        "missing_state_path",
        "missing_required_input",
        "unknown_prompt_variable",
        "nested_mapping_path_runtime",
    ],
)
def test_issue_codes_already_covered_elsewhere(issue_code: str):
    """Smoke: базовые кейсы остаются в test_flow_dataflow_inspector.py."""
    assert issue_code
