"""
Дерево spans по parent_span_id (порядок siblings — start_time).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from core.tracing.models import TraceSpanRecord
from core.types import JsonObject, require_json_object

TraceTreeInput = TraceSpanRecord | JsonObject


def _span_tree_payload(span: TraceTreeInput) -> JsonObject:
    if isinstance(span, TraceSpanRecord):
        return span.to_json_object()
    return span


def _parse_span_start_time(span: JsonObject) -> datetime:
    raw = span.get("start_time")
    if raw is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    if not isinstance(raw, str):
        raise ValueError("span.start_time must be an ISO string or null")
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _span_exec_sort_key(span: JsonObject) -> tuple[datetime, str]:
    raw_span_id = span.get("span_id")
    if not isinstance(raw_span_id, str):
        raise ValueError("span.span_id must be a string")
    return (_parse_span_start_time(span), raw_span_id)


def _sort_span_tree_execution_order(nodes: list[JsonObject]) -> None:
    nodes.sort(key=_span_exec_sort_key)
    for node in nodes:
        children = node.get("children")
        if isinstance(children, list) and children:
            child_nodes: list[JsonObject] = []
            for child in children:
                if not isinstance(child, dict):
                    raise ValueError("span.children items must be objects")
                child_nodes.append(require_json_object(child, "span.children[]"))
            _sort_span_tree_execution_order(child_nodes)
            node["children"] = child_nodes


def build_span_tree(spans: Sequence[TraceTreeInput]) -> list[JsonObject]:
    """
    Строит дерево spans из плоского списка.
    Siblings сортируются по start_time.
    """
    if not spans:
        return []

    ordered = sorted((_span_tree_payload(span) for span in spans), key=_span_exec_sort_key)
    span_map: dict[str, JsonObject] = {}
    for span in ordered:
        span_id = span.get("span_id")
        if not isinstance(span_id, str):
            raise ValueError("span.span_id must be a string")
        node: JsonObject = dict(span)
        node["children"] = []
        span_map[span_id] = node
    roots: list[JsonObject] = []

    for span in ordered:
        span_id = span.get("span_id")
        if not isinstance(span_id, str):
            raise ValueError("span.span_id must be a string")
        parent_id = span.get("parent_span_id")
        if isinstance(parent_id, str) and parent_id in span_map:
            children = span_map[parent_id].get("children")
            if not isinstance(children, list):
                raise ValueError("span.children must be an array")
            children.append(span_map[span_id])
        else:
            roots.append(span_map[span_id])

    _sort_span_tree_execution_order(roots)
    return roots
