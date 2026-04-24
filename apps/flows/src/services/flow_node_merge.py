"""
Слияние нод при сохранении: патч только с pos_x/pos_y не затирает type/code/llm.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_CANVAS_PLACEMENT_KEYS = frozenset({"pos_x", "pos_y"})


def _is_canvas_placement_only(inc: Any) -> bool:
    if not isinstance(inc, dict):
        return False
    if not inc:
        return True
    return set(inc.keys()) <= _CANVAS_PLACEMENT_KEYS


def node_config_is_canvas_placement_only(inc: Any) -> bool:
    """True если в конфиге ноды только pos_x/pos_y (или пустой dict)."""
    return _is_canvas_placement_only(inc)


def _node_has_non_canvas_fields(prev: Any) -> bool:
    if not isinstance(prev, dict) or not prev:
        return False
    for k, v in prev.items():
        if k in _CANVAS_PLACEMENT_KEYS:
            continue
        if v is None or v == "" or v == [] or v == {}:
            continue
        return True
    return False


def merge_incoming_node_dict_for_persist(
    incoming_map: Dict[str, Any],
    previous_map: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    base = previous_map or {}
    out: Dict[str, Any] = {}
    for node_id, inc in incoming_map.items():
        if not _is_canvas_placement_only(inc):
            out[node_id] = inc
            continue
        prev = base.get(node_id)
        if _node_has_non_canvas_fields(prev) and isinstance(prev, dict) and isinstance(inc, dict):
            merged = dict(prev)
            merged.update(inc)
            out[node_id] = merged
        else:
            out[node_id] = inc
    return out
