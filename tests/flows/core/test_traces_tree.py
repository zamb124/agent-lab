"""Порядок spans в дереве трейсов — по времени выполнения."""

from datetime import datetime, timezone

import pytest

from core.tracing.span_tree import build_span_tree


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@pytest.mark.parametrize(
    "flat_input_order",
    ["reverse", "forward", "mixed"],
)
def test_build_span_tree_siblings_execution_order(flat_input_order: str) -> None:
    """
    Дети одного родителя в UI должны идти по start_time, а не в порядке строк из БД.
    """
    t0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0.replace(second=1)
    t2 = t0.replace(second=2)

    flow_id = "span-flow"
    sup_id = "node-supervisor"
    llm2_id = "node-llm2"

    flow_span = {
        "span_id": "root",
        "parent_span_id": None,
        "operation_name": f"flow.{flow_id}",
        "start_time": _iso(t0),
    }
    supervisor = {
        "span_id": sup_id,
        "parent_span_id": "root",
        "operation_name": "node.llm_node.supervisor",
        "start_time": _iso(t1),
    }
    llm2 = {
        "span_id": llm2_id,
        "parent_span_id": "root",
        "operation_name": "node.llm_node.llm_node_2",
        "start_time": _iso(t2),
    }

    if flat_input_order == "reverse":
        flat = [flow_span, llm2, supervisor]
    elif flat_input_order == "forward":
        flat = [flow_span, supervisor, llm2]
    else:
        flat = [supervisor, flow_span, llm2]

    tree = build_span_tree(flat)
    assert len(tree) == 1
    root = tree[0]
    assert root["span_id"] == "root"
    children = root["children"]
    names = [c["operation_name"] for c in children]
    assert names == [
        "node.llm_node.supervisor",
        "node.llm_node.llm_node_2",
    ]
