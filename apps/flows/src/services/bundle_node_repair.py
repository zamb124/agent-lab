"""
Починка нод, в БД у которых остались только pos_x/pos_y: подстановка семантики из flow.json bundle.

Срабатывает для flow с source=file, у которого есть каталог в apps/flows/bundles/<id>/.
"""

from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from apps.flows.src.services.flow_node_merge import node_config_is_canvas_placement_only
from apps.flows.src.utils.merge import deep_merge

# apps/flows/ — родитель `src/services/`
_FLOWS_ROOT = Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def _registry_flow_to_bundle() -> Dict[str, str]:
    """
    flow_id (из flow.json) -> bundle_id по registry.yaml.
    """
    path = _FLOWS_ROOT / "registry.yaml"
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries = data.get("flows")
    if not isinstance(entries, list):
        return {}
    out: Dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, str):
            bundle_id = entry
        elif isinstance(entry, dict):
            bundle_id = entry.get("id")
        else:
            continue
        if not isinstance(bundle_id, str) or not bundle_id:
            continue
        flow_path = _FLOWS_ROOT / "bundles" / bundle_id / "flow.json"
        if not flow_path.is_file():
            continue
        with open(flow_path, "r", encoding="utf-8") as jf:
            raw = json.load(jf)
        fid = raw.get("flow_id") or raw.get("id")
        if isinstance(fid, str) and fid:
            out[fid] = bundle_id
    return out


@lru_cache(maxsize=64)
def _bundle_top_level_nodes(flow_id: str) -> Optional[Dict[str, Any]]:
    bmap = _registry_flow_to_bundle()
    bundle_id = bmap.get(flow_id)
    if not bundle_id:
        return None
    path = _FLOWS_ROOT / "bundles" / bundle_id / "flow.json"
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        return None
    return nodes


def get_bundle_base_nodes_for_flow(flow_id: str) -> Optional[Dict[str, Any]]:
    """Секция ``nodes`` из flow.json bundle для flow_id (если flow зарегистрирован)."""
    return _bundle_top_level_nodes(flow_id)


def repair_effective_nodes_from_bundle(
    flow_id: str, source: Optional[str], nodes: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Для source=file: подмешивает в «пустые» (только canvas) ноды конфиг из bundle flow.json.
    """
    if (source or "manual") != "file":
        return nodes
    canonical = _bundle_top_level_nodes(flow_id)
    if not canonical:
        return nodes
    return repair_node_map_with_canonical_top_level(nodes, canonical)


def repair_node_map_with_canonical_top_level(
    nodes: Dict[str, Any], canonical: Dict[str, Any]
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for node_id, cfg in nodes.items():
        if not node_config_is_canvas_placement_only(cfg):
            out[node_id] = deepcopy(cfg) if isinstance(cfg, dict) else cfg
            continue
        can = canonical.get(node_id)
        if not isinstance(can, dict) or not can or node_config_is_canvas_placement_only(can):
            out[node_id] = deepcopy(cfg) if isinstance(cfg, dict) else cfg
            continue
        out[node_id] = deep_merge(deepcopy(can), deepcopy(cfg))
    return out
