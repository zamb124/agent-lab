"""
LLM resource island: нода type=resource с единственной привязкой к ресурсу llm.

Валидация ветки/flow; слой поля llm на branch.resource definitions при резолве.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from apps.flows.src.models.flow_config import Edge
from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.models.resource import (
    LLMResourceConfig,
    LLMResourcePatch,
    ResourceReference,
    ResourceType,
)
from apps.flows.src.resources.merge_llm import (
    merge_llm_resource_config_with_patch,
    merge_llm_resource_patch_dicts,
)


def _type_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, ResourceType):
        return value.value
    return str(value)


def is_llm_resource_island_dict(
    node: Mapping[str, Any],
    merged_branch_resources: Mapping[str, Any],
) -> bool:
    """merged_branch_resources — flow+skill ресурсы по ключам (dict или ResourceReference)."""
    if node.get("type") != "resource":
        return False
    nr = node.get("resources")
    if not isinstance(nr, dict) or len(nr) != 1:
        return False
    (bind_key, ref_raw), = nr.items()
    ref: dict[str, Any] = ref_raw if isinstance(ref_raw, dict) else {}
    inline_t = ref.get("type")
    if inline_t is not None:
        return _type_str(inline_t) == ResourceType.LLM.value
    rid = ref.get("resource_id")
    lookup = rid if isinstance(rid, str) and rid.strip() else str(bind_key)
    if lookup not in merged_branch_resources:
        return False
    br = merged_branch_resources[lookup]
    if isinstance(br, ResourceReference):
        if br.type is None:
            return False
        return br.type == ResourceType.LLM
    if isinstance(br, dict):
        return _type_str(br.get("type")) == ResourceType.LLM.value
    return False


def resource_node_has_non_empty_llm(node: Mapping[str, Any]) -> bool:
    v = node.get("llm")
    if v is None:
        return False
    if isinstance(v, dict) and len(v) == 0:
        return False
    return True


def llm_resource_island_node_ids(
    nodes: Mapping[str, Mapping[str, Any]] | None,
    merged_resources: Mapping[str, Any],
) -> set[str]:
    if not nodes:
        return set()
    return {
        nid
        for nid, n in nodes.items()
        if isinstance(n, dict) and is_llm_resource_island_dict(n, merged_resources)
    }


def _edge_pair(edge: Any) -> tuple[str, str | None]:
    if isinstance(edge, Edge):
        return edge.from_node, edge.to_node
    if isinstance(edge, dict):
        fn = edge.get("from_node") if edge.get("from_node") is not None else edge.get("from")
        tn = edge.get("to_node") if "to_node" in edge else edge.get("to")
        if not isinstance(fn, str) or not fn.strip():
            return "", None
        if tn is not None and (not isinstance(tn, str) or not tn.strip()):
            return fn.strip(), None
        return fn.strip(), tn if isinstance(tn, str) else None
    return "", None


def validate_llm_resource_islands_in_graph(
    *,
    nodes: dict[str, dict[str, Any]] | None,
    edges: Sequence[Any] | None,
    flow_resources: Mapping[str, Any],
    skill_resources: Mapping[str, Any] | None,
    entry: str | None,
) -> None:
    """Вызывать после сборки maps ресурсов для ветки (flow ∪ skill по ключам)."""
    if not nodes:
        return
    merged: dict[str, Any] = dict(flow_resources or {})
    if skill_resources:
        merged.update(dict(skill_resources))
    island_ids = llm_resource_island_node_ids(nodes, merged)
    for nid, n in nodes.items():
        if not isinstance(n, dict):
            continue
        if n.get("type") != "resource":
            continue
        if not is_llm_resource_island_dict(n, merged) and resource_node_has_non_empty_llm(n):
            raise ValueError(
                f"resource node '{nid}': поле llm допустимо только для LLM resource island "
                f"(ровно одна привязка resources к типу llm)"
            )
    for e in list(edges or []):
        fn, tn = _edge_pair(e)
        if fn in island_ids:
            raise ValueError(
                f"ребро с LLM resource island запрещено: исходная нода '{fn}'"
            )
        if tn is not None and tn in island_ids:
            raise ValueError(
                f"ребро с LLM resource island запрещено: целевая нода '{tn}'"
            )
    if entry is not None and entry.strip() and entry in island_ids:
        raise ValueError(
            f"entry не может быть LLM resource island: '{entry}'"
        )


def _resource_ref_plain(ref_raw: Any) -> ResourceReference:
    if isinstance(ref_raw, ResourceReference):
        return ref_raw
    if isinstance(ref_raw, dict):
        return ResourceReference.model_validate(ref_raw)
    raise ValueError(f"ожидался ResourceReference или dict, получено {type(ref_raw)!r}")


def _patch_llm_dict_into_bucket(
    bucket: dict[str, Any],
    bind_key: str,
    llm_raw: Any,
) -> None:
    if llm_raw is None:
        return
    if isinstance(llm_raw, dict) and len(llm_raw) == 0:
        return
    if bind_key not in bucket:
        return
    ref = _resource_ref_plain(bucket[bind_key])
    ov = NodeLLMConfig.model_validate(llm_raw)
    allowed = frozenset(LLMResourcePatch.model_fields.keys())
    patch_dict = {
        k: v
        for k, v in ov.model_dump(exclude_none=True, mode="json").items()
        if k in allowed and k != "llm_resource_key"
    }
    if not patch_dict:
        return
    if ref.is_inline:
        if ref.type != ResourceType.LLM:
            return
        base = merge_llm_resource_config_with_patch(
            LLMResourceConfig.model_validate(ref.config or {}),
            patch_dict,
        )
        updated = ref.model_copy(
            update={"config": base.model_dump(mode="json", exclude_none=True)}
        )
        bucket[bind_key] = updated.model_dump(exclude_none=True, mode="json")
        return
    prev = merge_llm_resource_patch_dicts(
        dict(ref.config) if ref.config else None,
        patch_dict,
    )
    updated = ref.model_copy(update={"config": prev or None})
    bucket[bind_key] = updated.model_dump(exclude_none=True, mode="json")


def overlay_llm_resource_islands_on_resource_maps(
    flow_resources: dict[str, Any],
    skill_resources: dict[str, Any] | None,
    effective_nodes: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Копии карт ресурсов с подмешиванием node.llm островов в LLM resource config."""
    fr = copy.deepcopy(flow_resources)
    sr = copy.deepcopy(skill_resources) if skill_resources else None
    merged_lookup: dict[str, Any] = {**fr, **(sr or {})}
    for _nid, n in effective_nodes.items():
        if not isinstance(n, dict):
            continue
        if not is_llm_resource_island_dict(n, merged_lookup):
            continue
        if not resource_node_has_non_empty_llm(n):
            continue
        nr = n.get("resources")
        if not isinstance(nr, dict) or len(nr) != 1:
            continue
        (bind_key, _), = nr.items()
        llm_raw = n.get("llm")
        if bind_key in (sr or {}):
            assert sr is not None
            _patch_llm_dict_into_bucket(sr, str(bind_key), llm_raw)
        elif str(bind_key) in fr:
            _patch_llm_dict_into_bucket(fr, str(bind_key), llm_raw)
    return fr, sr
