"""
Log-mirror завершённых platform spans в Loki для Grafana product metrics.

Spans сохраняются в Postgres (admin tracing UI); этот модуль дублирует
completion-события в structured logs для LogQL quantiles.
"""

from __future__ import annotations

import core.tracing.attributes as attr
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_OPERATION_FINISHED,
    EVENT_TOOL_CALL_FINISHED,
    LOG_FLOW_ID,
    LOG_HANDOFF_DEPTH,
    LOG_HANDOFF_TARGET_FLOW_ID,
    LOG_HITL_QUEUE_SLUG,
    LOG_HITL_WORK_ITEM_ID,
    LOG_MCP_METHOD,
    LOG_MCP_SERVER_ID,
    LOG_MCP_TOOL_NAME,
    LOG_NODE_ID,
    LOG_NODE_TYPE,
    LOG_OPERATION_CATEGORY,
    LOG_OPERATION_DURATION_MS,
    LOG_OPERATION_NAME,
    LOG_OPERATION_STATUS,
    LOG_RAG_DOCUMENT_ID,
    LOG_RAG_STAGE,
    LOG_TASK_ID,
    LOG_TOOL_DURATION_MS,
    LOG_TOOL_ERROR,
    LOG_TOOL_IS_AGENT,
    LOG_TOOL_NAME,
)
from core.types import JsonObject, JsonValue

_logger = get_logger(__name__)

_OPERATION_LOG_MIRROR_SKIP = "skip"
_OPERATION_LOG_MIRROR_ALWAYS = "always"

_SKIP_OPERATION_PREFIXES = (
    "tool.",
    "llm.",
    "llm_node.",
    "react.iteration.",
    "interrupt.",
)

_SKIP_OPERATION_NAMES = frozenset(
    {
        "flows.memory.summarize",
    }
)

_SKIP_OPERATION_CATEGORIES = frozenset(
    {
        "llm",
    }
)

_ATTR_TO_LOG_KEY: dict[str, str] = {
    attr.ATTR_OPERATION_CATEGORY: LOG_OPERATION_CATEGORY,
    attr.ATTR_FLOW_ID: LOG_FLOW_ID,
    attr.ATTR_TASK_ID: LOG_TASK_ID,
    attr.ATTR_MCP_SERVER_ID: LOG_MCP_SERVER_ID,
    attr.ATTR_MCP_METHOD: LOG_MCP_METHOD,
    attr.ATTR_MCP_TOOL_NAME: LOG_MCP_TOOL_NAME,
    attr.ATTR_TOOL_NAME: LOG_TOOL_NAME,
    attr.ATTR_TOOL_DURATION_MS: LOG_TOOL_DURATION_MS,
    attr.ATTR_TOOL_ERROR: LOG_TOOL_ERROR,
    attr.ATTR_TOOL_IS_AGENT: LOG_TOOL_IS_AGENT,
    attr.ATTR_NODE_TYPE: LOG_NODE_TYPE,
    attr.ATTR_NODE_ID: LOG_NODE_ID,
    attr.ATTR_RAG_DOCUMENT_ID: LOG_RAG_DOCUMENT_ID,
    attr.ATTR_RAG_STAGE: LOG_RAG_STAGE,
    attr.ATTR_HANDOFF_DEPTH: LOG_HANDOFF_DEPTH,
    attr.ATTR_HANDOFF_TARGET_FLOW_ID: LOG_HANDOFF_TARGET_FLOW_ID,
    attr.ATTR_HITL_QUEUE_SLUG: LOG_HITL_QUEUE_SLUG,
    attr.ATTR_HITL_WORK_ITEM_ID: LOG_HITL_WORK_ITEM_ID,
}


def _json_scalar(value: JsonValue) -> str | int | float | bool | None:
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return None
    return str(value)


def should_mirror_operation_finished(
    operation_name: str,
    span_attributes: JsonObject,
) -> bool:
    log_mirror = span_attributes.get(attr.ATTR_OPERATION_LOG_MIRROR)
    if log_mirror == _OPERATION_LOG_MIRROR_SKIP:
        return False
    if log_mirror == _OPERATION_LOG_MIRROR_ALWAYS:
        return True
    if operation_name in _SKIP_OPERATION_NAMES:
        return False
    if any(operation_name.startswith(prefix) for prefix in _SKIP_OPERATION_PREFIXES):
        return False
    category = span_attributes.get(attr.ATTR_OPERATION_CATEGORY)
    if isinstance(category, str) and category in _SKIP_OPERATION_CATEGORIES:
        return False
    if isinstance(category, str) and category.strip() != "":
        return True
    if operation_name.startswith("node."):
        return True
    return len(operation_name.split(".")) >= 3


def _mirror_fields_from_span_attributes(span_attributes: JsonObject) -> JsonObject:
    fields: JsonObject = {}
    for attr_key, log_key in _ATTR_TO_LOG_KEY.items():
        raw_value = span_attributes.get(attr_key)
        scalar = _json_scalar(raw_value)
        if scalar is not None:
            fields[log_key] = scalar
    return fields


def log_operation_finished(
    *,
    operation_name: str,
    duration_ms: int,
    status: str,
    span_attributes: JsonObject,
) -> None:
    if not should_mirror_operation_finished(operation_name, span_attributes):
        return
    fields: JsonObject = {
        LOG_OPERATION_NAME: operation_name,
        LOG_OPERATION_DURATION_MS: duration_ms,
        LOG_OPERATION_STATUS: status,
    }
    category = span_attributes.get(attr.ATTR_OPERATION_CATEGORY)
    if isinstance(category, str) and category.strip() != "":
        fields[LOG_OPERATION_CATEGORY] = category.strip()
    elif operation_name.startswith("node."):
        fields[LOG_OPERATION_CATEGORY] = "flow_node"
    fields.update(_mirror_fields_from_span_attributes(span_attributes))
    _logger.info(EVENT_OPERATION_FINISHED, **fields)


def log_tool_call_finished(
    *,
    tool_name: str,
    duration_ms: float,
    error: str | None,
    span_attributes: JsonObject,
) -> None:
    status = "error" if error else "ok"
    fields: JsonObject = {
        LOG_TOOL_NAME: tool_name,
        LOG_TOOL_DURATION_MS: round(duration_ms, 3),
        LOG_OPERATION_STATUS: status,
    }
    if error:
        fields[LOG_TOOL_ERROR] = error[:500]
    is_agent = span_attributes.get(attr.ATTR_TOOL_IS_AGENT)
    if isinstance(is_agent, bool):
        fields[LOG_TOOL_IS_AGENT] = is_agent
    task_id = span_attributes.get(attr.ATTR_TASK_ID)
    if isinstance(task_id, str) and task_id.strip() != "":
        fields[LOG_TASK_ID] = task_id.strip()
    flow_id = span_attributes.get(attr.ATTR_FLOW_ID)
    if isinstance(flow_id, str) and flow_id.strip() != "":
        fields[LOG_FLOW_ID] = flow_id.strip()
    _logger.info(EVENT_TOOL_CALL_FINISHED, **fields)
