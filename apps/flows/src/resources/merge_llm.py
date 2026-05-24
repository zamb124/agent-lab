"""Слияние LLMResourceConfig с типизированным patch и NodeLLMConfig."""

from __future__ import annotations

from apps.flows.src.models.node_config import NodeLLMConfig
from apps.flows.src.models.resource import LLMResourceConfig, LLMResourcePatch
from core.types import JsonObject, require_json_object


def deep_merge_optional_dicts(
    base: JsonObject | None,
    override: JsonObject | None,
) -> JsonObject | None:
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
            out[k] = deep_merge_optional_dicts(
                require_json_object(out[k], "llm_resource.deep_merge.base"),
                require_json_object(v, "llm_resource.deep_merge.override"),
            )
        else:
            out[k] = v
    return out


def merge_llm_resource_patch_dicts(
    base_patch: JsonObject | None,
    overlay_raw: JsonObject | None,
) -> JsonObject:
    """
    Два частичных слоя patch (например ref.config + оверлей острова LLM).
    Те же правила, что merge_llm_resource_config_with_patch для dict-уровня.
    """
    d: JsonObject = dict(base_patch or {})
    if not overlay_raw:
        return d
    patch = LLMResourcePatch.model_validate(overlay_raw)
    pd = require_json_object(
        patch.model_dump(exclude_none=True, mode="json"),
        "llm_resource.patch",
    )
    for name, val in pd.items():
        if name == "extra_request_body":
            merged = deep_merge_optional_dicts(
                require_json_object(d["extra_request_body"], "llm_resource.extra_request_body")
                if isinstance(d.get("extra_request_body"), dict)
                else None,
                patch.extra_request_body,
            )
            if merged is not None:
                d["extra_request_body"] = merged
            continue
        if name == "extra_request_headers":
            if patch.extra_request_headers is None:
                continue
            existing = d.get("extra_request_headers")
            base_headers = require_json_object(
                existing,
                "llm_resource.extra_request_headers",
            ) if isinstance(existing, dict) else {}
            d["extra_request_headers"] = {
                **base_headers,
                **patch.extra_request_headers,
            }
            continue
        d[name] = val
    return d


def merge_llm_resource_config_with_patch(
    base: LLMResourceConfig,
    patch_raw: JsonObject | None,
) -> LLMResourceConfig:
    if not patch_raw:
        return base
    patch = LLMResourcePatch.model_validate(patch_raw)
    d = require_json_object(
        base.model_dump(exclude_none=False, mode="json"),
        "llm_resource.base",
    )
    pd = require_json_object(
        patch.model_dump(exclude_none=True, mode="json"),
        "llm_resource.patch",
    )
    for name, val in pd.items():
        if name == "extra_request_body":
            merged = deep_merge_optional_dicts(
                require_json_object(d["extra_request_body"], "llm_resource.extra_request_body")
                if isinstance(d.get("extra_request_body"), dict)
                else None,
                patch.extra_request_body,
            )
            if merged is not None:
                d["extra_request_body"] = merged
            continue
        if name == "extra_request_headers":
            if patch.extra_request_headers is None:
                continue
            existing = d.get("extra_request_headers")
            base_headers = require_json_object(
                existing,
                "llm_resource.extra_request_headers",
            ) if isinstance(existing, dict) else {}
            d["extra_request_headers"] = {**base_headers, **patch.extra_request_headers}
            continue
        d[name] = val
    return LLMResourceConfig.model_validate(d)


def merge_llm_resource_into_node_config(
    base: LLMResourceConfig,
    patch: NodeLLMConfig,
) -> NodeLLMConfig:
    base_dict = require_json_object(
        base.model_dump(exclude_none=True, mode="json"),
        "llm_resource.base",
    )
    patch_dump = require_json_object(
        patch.model_dump(exclude_none=False, mode="json"),
        "llm_resource.node_patch",
    )
    for name, val in patch_dump.items():
        if name == "llm_resource_key":
            continue
        if val is None:
            continue
        if name == "extra_request_body" and patch.extra_request_body is not None:
            existing = base_dict.get("extra_request_body")
            base_dict["extra_request_body"] = deep_merge_optional_dicts(
                require_json_object(existing, "llm_resource.extra_request_body")
                if isinstance(existing, dict)
                else None,
                patch.extra_request_body,
            )
            continue
        if name == "extra_request_headers" and patch.extra_request_headers is not None:
            existing = base_dict.get("extra_request_headers")
            base_headers = require_json_object(
                existing,
                "llm_resource.extra_request_headers",
            ) if isinstance(existing, dict) else {}
            base_dict["extra_request_headers"] = {
                **base_headers,
                **patch.extra_request_headers,
            }
            continue
        base_dict[name] = val
    return NodeLLMConfig.model_validate(base_dict)


merge_llm_resource_into_node_override = merge_llm_resource_into_node_config
