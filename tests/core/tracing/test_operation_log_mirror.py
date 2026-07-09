"""Unit tests for operation_finished log-mirror."""

from __future__ import annotations

import core.tracing.attributes as attr
from core.tracing.operation_log_mirror import should_mirror_operation_finished


def test_should_mirror_traced_operation_with_category() -> None:
    assert should_mirror_operation_finished(
        "flows.mcp.tool_call",
        {attr.ATTR_OPERATION_CATEGORY: "mcp"},
    )


def test_should_skip_tool_span_operation_name() -> None:
    assert not should_mirror_operation_finished(
        "tool.calculator",
        {attr.ATTR_OPERATION_CATEGORY: "tool"},
    )


def test_should_mirror_node_span_operation_name() -> None:
    assert should_mirror_operation_finished(
        "node.llm.my_node",
        {},
    )


def test_should_skip_when_log_mirror_disabled() -> None:
    assert not should_mirror_operation_finished(
        "rag.search.namespace",
        {
            attr.ATTR_OPERATION_CATEGORY: "rag_search",
            attr.ATTR_OPERATION_LOG_MIRROR: "skip",
        },
    )
