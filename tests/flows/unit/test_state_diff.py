"""Unit-тесты diff state для canvas preview."""

from apps.flows.src.runtime.state_diff import (
    CANVAS_DIFF_LIMIT,
    build_canvas_result_preview,
    compute_state_diff,
    infer_primary_field,
    summarize_canvas_value,
    top_state_diff_items,
)


def test_compute_state_diff_skips_messages() -> None:
    old = {"response": None, "messages": []}
    new = {"response": "hello", "messages": [{"role": "user", "content": "hi"}]}
    items = compute_state_diff(old, new)
    paths = [item.path for item in items]
    assert "response" in paths
    assert "messages" not in paths


def test_top_state_diff_items_limits_count() -> None:
    old = {"a": 1, "b": 1, "c": 1}
    new = {"a": 2, "b": 2, "c": 2, "d": 2, "e": 2, "f": 2, "g": 2, "h": 2, "i": 2}
    items = top_state_diff_items(compute_state_diff(old, new), limit=CANVAS_DIFF_LIMIT)
    assert len(items) == CANVAS_DIFF_LIMIT


def test_infer_primary_field_prefers_response() -> None:
    after = {"response": "ok", "result": 1}
    field = infer_primary_field(after, [])
    assert field == "response"


def test_summarize_canvas_value_status_map() -> None:
    text = summarize_canvas_value({"index": {"ok": True, "latency_ms": 14770}})
    assert "index: ok" in text
    assert "14770 ms" in text
    assert "{" not in text


def test_build_canvas_result_preview_mcp() -> None:
    after = {"mcp_result": {"hits": 2}}
    diff_items = compute_state_diff({}, after)
    preview = build_canvas_result_preview("mcp", after, diff_items, "mcp_result")
    assert preview == "1 fields"


def test_build_canvas_result_preview_llm_node() -> None:
    after = {"response": "Hello from LLM"}
    preview = build_canvas_result_preview("llm_node", after, [], "response")
    assert preview == "Hello from LLM"
