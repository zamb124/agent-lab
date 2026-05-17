"""
Дерево spans по parent_span_id (порядок siblings — start_time).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List


def _parse_span_start_time(span: Dict[str, Any]) -> datetime:
    raw = span.get("start_time")
    if raw is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    text = str(raw).replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _span_exec_sort_key(span: Dict[str, Any]) -> tuple[datetime, str]:
    return (_parse_span_start_time(span), span.get("span_id") or "")


def _sort_span_tree_execution_order(nodes: List[Dict[str, Any]]) -> None:
    nodes.sort(key=_span_exec_sort_key)
    for node in nodes:
        children = node.get("children")
        if children:
            _sort_span_tree_execution_order(children)


def build_span_tree(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Строит дерево spans из плоского списка.
    Siblings сортируются по start_time.
    """
    if not spans:
        return []

    ordered = sorted(spans, key=_span_exec_sort_key)
    span_map = {s["span_id"]: {**s, "children": []} for s in ordered}
    roots: List[Dict[str, Any]] = []

    for span in ordered:
        span_id = span["span_id"]
        parent_id = span.get("parent_span_id")
        if parent_id and parent_id in span_map:
            span_map[parent_id]["children"].append(span_map[span_id])
        else:
            roots.append(span_map[span_id])

    _sort_span_tree_execution_order(roots)
    return roots
