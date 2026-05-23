"""Layered resolver for platform LLM context policies."""

from __future__ import annotations

from typing import Any

from core.config import get_settings
from core.context import get_context
from core.llm_context.merge import deep_merge_dict
from core.llm_context.models import (
    LLMContextConfig,
    LLMContextPatch,
    LLMContextProfile,
)

_COMPANY_AI_METADATA_KEY = "ai_providers"


def _patch_to_dict(config: LLMContextConfig, patch: LLMContextPatch | dict[str, Any]) -> dict[str, Any]:
    typed = patch if isinstance(patch, LLMContextPatch) else LLMContextPatch.model_validate(patch)
    patch_data = typed.model_dump(mode="python", exclude_none=True)
    profile_key = patch_data.pop("profile", None)
    expanded: dict[str, Any] = {}

    if profile_key is not None:
        profile = config.profiles.get(profile_key)
        if profile is None:
            raise ValueError(f"LLM context profile {profile_key!r} is not configured")
        expanded = profile.model_dump(mode="python")

    budget_value = patch_data.get("budget")
    if isinstance(budget_value, str):
        budget = config.budgets.get(budget_value)
        if budget is None:
            raise ValueError(f"LLM context budget {budget_value!r} is not configured")
        patch_data["budget"] = budget.model_dump(mode="python")

    retrieval_value = patch_data.get("retrieval")
    if isinstance(retrieval_value, str):
        patch_data["retrieval"] = {"mode": retrieval_value}

    return deep_merge_dict(expanded, patch_data)


def resolve_llm_context_policy(
    *,
    config: LLMContextConfig | None = None,
    company: LLMContextPatch | dict[str, Any] | None = None,
    resource: LLMContextPatch | dict[str, Any] | None = None,
    node: LLMContextPatch | dict[str, Any] | None = None,
    call: LLMContextPatch | dict[str, Any] | None = None,
) -> LLMContextProfile:
    """
    Resolve context behavior in canonical platform order.

    Order: platform default profile -> company -> resource -> node -> inline call.
    Later layers are intentionally narrow patches over the resolved policy.
    """
    effective_config = config or get_settings().llm_context
    base = effective_config.profiles[effective_config.default_profile]
    merged = base.model_dump(mode="python")
    for layer in (company, resource, node, call):
        if layer is None:
            continue
        merged = deep_merge_dict(merged, _patch_to_dict(effective_config, layer))
    return LLMContextProfile.model_validate(merged)


def resolve_company_llm_context_patch() -> LLMContextPatch | None:
    """Read company-level context patch from active company metadata."""
    ctx = get_context()
    company = ctx.active_company if ctx is not None else None
    metadata = getattr(company, "metadata", None) or {}
    if not isinstance(metadata, dict):
        raise ValueError("company.metadata must be dict")
    raw_ai = metadata.get(_COMPANY_AI_METADATA_KEY)
    if raw_ai is None:
        return None
    if not isinstance(raw_ai, dict):
        raise ValueError(f"company.metadata[{_COMPANY_AI_METADATA_KEY!r}] must be object")
    raw_patch = raw_ai.get("llm_context")
    if raw_patch is None:
        return None
    return LLMContextPatch.model_validate(raw_patch)


__all__ = ["resolve_company_llm_context_patch", "resolve_llm_context_policy"]
