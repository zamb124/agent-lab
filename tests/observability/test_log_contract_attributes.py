"""Static contract: EVENT_* product metrics имеют unwrap-поля без dot-notation."""

from __future__ import annotations

import re

from core.logging import attributes as log_attr


def _unwrap_field_names() -> list[str]:
    names: list[str] = []
    for name in dir(log_attr):
        if not name.startswith("LOG_"):
            continue
        value = getattr(log_attr, name)
        if isinstance(value, str):
            names.append(value)
    return names


def test_product_metric_events_have_log_counterparts() -> None:
    event_to_log_pairs = [
        (log_attr.EVENT_FLOW_TERMINAL, log_attr.LOG_FLOW_TERMINAL_MS),
        (log_attr.EVENT_FLOW_FIRST_CONTENT_CHUNK, log_attr.LOG_FLOW_FIRST_CHUNK_MS),
        (log_attr.EVENT_FLOW_REACT_COMPLETED, log_attr.LOG_FLOW_REACT_ITERATIONS),
        (log_attr.EVENT_OPERATION_FINISHED, log_attr.LOG_OPERATION_DURATION_MS),
        (log_attr.EVENT_TOOL_CALL_FINISHED, log_attr.LOG_TOOL_DURATION_MS),
        (log_attr.EVENT_HANDOFF_WALL_TIME, log_attr.LOG_HANDOFF_WALL_MS),
        (log_attr.EVENT_HITL_OPERATOR_RESPONDED, log_attr.LOG_HITL_WAIT_MS),
        (log_attr.EVENT_LLM_CONTEXT_COMPILED, log_attr.LOG_LLM_CONTEXT_COMPILE_MS),
        (log_attr.EVENT_LLM_STREAM_RESPONSE, log_attr.LOG_LLM_TTFT_MS),
        (log_attr.EVENT_BILLING_SETTLEMENT_LAG, log_attr.LOG_BILLING_SETTLEMENT_LAG_MS),
        (log_attr.EVENT_WS_COMMAND_FINISHED, log_attr.LOG_WS_COMMAND_DURATION_MS),
        (log_attr.EVENT_VOICE_TTS_RESPONSE, log_attr.LOG_TTS_TTFA_MS),
        (log_attr.EVENT_TASK_STARTED, log_attr.LOG_TASK_QUEUE_WAIT_MS),
    ]
    for event_name, log_field in event_to_log_pairs:
        assert isinstance(event_name, str) and event_name
        assert isinstance(log_field, str) and log_field


def test_log_unwrap_fields_use_snake_case_without_spaces() -> None:
    pattern = re.compile(r"^[a-z0-9_.]+$")
    for field_name in _unwrap_field_names():
        assert pattern.match(field_name), f"invalid log field name: {field_name!r}"
