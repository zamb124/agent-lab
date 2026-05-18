"""Слияние LLMResourceConfig с типизированным patch и NodeLLMConfig."""

from __future__ import annotations

from typing import Any

from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.models.resource import LLMResourceConfig, LLMResourcePatch


def deep_merge_optional_dicts(
    base: dict[str, Any] | None,
    override: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if override is None:
        return base
    if base is None:
        return dict(override)
    out = dict(base)
    for k, v in override.items():
        if (
            k in out
            and isinstance(out[k], dict)
            and isinstance(v, dict)
        ):
            out[k] = deep_merge_optional_dicts(out[k], v)
        else:
            out[k] = v
    return out


def merge_llm_resource_patch_dicts(
    base_patch: dict[str, Any] | None,
    overlay_raw: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Два частичных слоя patch (например ref.config + оверлей острова LLM).
    Те же правила, что merge_llm_resource_config_with_patch для dict-уровня.
    """
    d = dict(base_patch or {})
    if not overlay_raw:
        return d
    patch = LLMResourcePatch.model_validate(overlay_raw)
    pd = patch.model_dump(exclude_none=True)
    for name, val in pd.items():
        if name == "extra_request_body":
            prev = d.get("extra_request_body")
            merged = deep_merge_optional_dicts(
                prev if isinstance(prev, dict) else None,
                val if isinstance(val, dict) else None,
            )
            if merged is not None:
                d["extra_request_body"] = merged
            continue
        if name == "extra_request_headers":
            hv = val if isinstance(val, dict) else None
            if hv is None:
                continue
            hb = d.get("extra_request_headers")
            d["extra_request_headers"] = {
                **(hb if isinstance(hb, dict) else {}),
                **hv,
            }
            continue
        d[name] = val
    return d


def merge_llm_resource_config_with_patch(
    base: LLMResourceConfig,
    patch_raw: dict[str, Any] | None,
) -> LLMResourceConfig:
    if not patch_raw:
        return base
    patch = LLMResourcePatch.model_validate(patch_raw)
    d = base.model_dump(exclude_none=False)
    pd = patch.model_dump(exclude_none=True)
    for name, val in pd.items():
        if name == "extra_request_body":
            merged = deep_merge_optional_dicts(
                d.get("extra_request_body") if isinstance(d.get("extra_request_body"), dict) else None,
                val if isinstance(val, dict) else None,
            )
            if merged is not None:
                d["extra_request_body"] = merged
            continue
        if name == "extra_request_headers":
            b = d.get("extra_request_headers")
            hb = b if isinstance(b, dict) else None
            hv = val if isinstance(val, dict) else None
            if hv is None:
                continue
            d["extra_request_headers"] = {**(hb or {}), **hv}
            continue
        d[name] = val
    return LLMResourceConfig.model_validate(d)


def merge_llm_resource_into_node_config(
    base: LLMResourceConfig,
    patch: NodeLLMConfig,
) -> NodeLLMConfig:
    base_dict = base.model_dump(exclude_none=True)
    for name, val in patch.model_dump(exclude_none=False).items():
        if name == "llm_resource_key":
            continue
        if val is None:
            continue
        if name == "extra_request_body" and isinstance(val, dict):
            prev = base_dict.get("extra_request_body")
            base_dict["extra_request_body"] = deep_merge_optional_dicts(
                prev if isinstance(prev, dict) else None,
                val,
            )
            continue
        if name == "extra_request_headers" and isinstance(val, dict):
            prev = base_dict.get("extra_request_headers")
            base_dict["extra_request_headers"] = {
                **(prev if isinstance(prev, dict) else {}),
                **val,
            }
            continue
        base_dict[name] = val
    return NodeLLMConfig.model_validate(base_dict)


merge_llm_resource_into_node_override = merge_llm_resource_into_node_config
