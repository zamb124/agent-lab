"""Строгое company-aware разрешение LLM config для flows runtime."""

from __future__ import annotations

from dataclasses import dataclass

from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig
from core.ai.resolver import (
    COST_ORIGIN_COMPANY,
    COST_ORIGIN_PLATFORM,
    AICapability,
    ResolvedLLM,
    resolve_custom_llm_provider_ref,
    resolve_llm_for_capability,
)
from core.clients.llm.config import LLMCallConfig
from core.company_ai import (
    CUSTOM_PROVIDER_REF_PREFIX,
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
)
from core.llm_model_routing import split_humanitec_llms_model_ref

_COMPANY_CONTROLLED_FIELDS = {
    "provider",
    "model",
    "api_key",
    "base_url",
    "folder_id",
    "fallback_models",
    "extra_request_headers",
    "extra_request_body",
}


@dataclass(frozen=True)
class EffectiveLLMConfig:
    """Итоговый LLM config и billing metadata, используемые flows runtime."""

    config: NodeLLMConfig
    capability: AICapability
    cost_origin: str
    billing_resource_name: str | None
    source: str


def llm_capability_from_node_config(node_config: NodeConfig | None) -> AICapability:
    cap_value = (
        node_config.llm_capability
        if node_config is not None and node_config.llm_capability
        else AICapability.LLM_CHAT.value
    )
    try:
        return AICapability(cap_value)
    except ValueError as exc:
        node_id = node_config.node_id if node_config is not None else "<unknown>"
        raise ValueError(
            f"LlmNode {node_id}: неизвестный llm_capability {cap_value!r}"
        ) from exc


def _base_config(node_config: NodeConfig | None) -> NodeLLMConfig:
    if node_config is not None and node_config.llm is not None:
        return node_config.llm
    return NodeLLMConfig()


def _apply_resolved_company_llm(
    base: NodeLLMConfig,
    resolved: ResolvedLLM,
) -> NodeLLMConfig:
    data = base.model_dump(mode="python", exclude_none=True)
    for field in _COMPANY_CONTROLLED_FIELDS:
        data.pop(field, None)
    data.update(
        {
            "provider": resolved.provider,
            "model": resolved.model,
            "api_key": resolved.api_key,
            "base_url": resolved.base_url,
            "folder_id": resolved.folder_id,
            "extra_request_headers": dict(resolved.extra_request_headers or {}) or None,
            "extra_request_body": dict(resolved.extra_request_body or {}) or None,
            "fallback_models": [
                fallback.model_dump(mode="json", exclude_none=True)
                for fallback in resolved.fallback_models or ()
            ]
            or None,
        }
    )
    return NodeLLMConfig.model_validate(data)


def _apply_resolved_custom_llm(
    base: NodeLLMConfig,
    resolved: ResolvedLLM,
) -> NodeLLMConfig:
    data = base.model_dump(mode="python", exclude_none=True)
    data.update(
        {
            "provider": resolved.provider,
            "model": resolved.model,
            "api_key": resolved.api_key,
            "base_url": resolved.base_url,
            "folder_id": resolved.folder_id or base.folder_id,
            "extra_request_headers": dict(resolved.extra_request_headers or {}) or None,
            "extra_request_body": dict(resolved.extra_request_body or {}) or None,
        }
    )
    return NodeLLMConfig.model_validate(data)


def _reject_node_fallbacks(
    node_config: NodeConfig | None,
    base: NodeLLMConfig,
) -> None:
    if not base.fallback_models:
        return
    node_id = node_config.node_id if node_config is not None else "<unknown>"
    message = (
        f"LlmNode {node_id}: llm.fallback_models в flow/node/resource config запрещены "
        + "для runtime. Настройте fallback policy в /settings -> AI providers для нужной capability."
    )
    raise ValueError(message)


def _validate_explicit_primary(
    node_config: NodeConfig | None,
    base: NodeLLMConfig,
    capability: AICapability,
) -> None:
    if base.provider == HUMANITEC_LLM_PROVIDER:
        if (
            base.model not in (None, HUMANITEC_LLM_AUTO_MODEL)
            and split_humanitec_llms_model_ref(base.model) is None
        ):
            raise ValueError(
                f"capability {capability.value}: provider=humanitec_llm поддерживает "
                + "model='auto' или provider-prefixed free-pool модель '<provider>:<model_id>'"
            )
        return
    if base.provider is None or base.model is None:
        node_id = node_config.node_id if node_config is not None else "<unknown>"
        message = (
            f"LlmNode {node_id}: нет company override для capability={capability.value}, "
            + "поэтому llm.provider и llm.model должны быть заданы явно. "
            + "Скрытый fallback на settings.llm.default_model запрещён."
        )
        raise ValueError(message)


def _fallback_models_billing_resource(
    fallback_models: list[LLMCallConfig] | None,
) -> str | None:
    if not fallback_models:
        return None
    return "llm:company_fallback_policy"


def resolve_effective_llm_config_for_node(
    node_config: NodeConfig | None,
) -> EffectiveLLMConfig:
    """Разрешает единственный LLM config, который flows runtime может исполнять.

    Company capability override всегда побеждает. provider/model и fallback_models
    из flow/node/resource никогда не перекрывают company settings. Без company
    override authored primary provider/model должны быть заданы явно, а node
    fallback_models отклоняются fail-closed.
    """
    capability = llm_capability_from_node_config(node_config)
    base = _base_config(node_config)

    resolved_company = resolve_llm_for_capability(capability)
    if resolved_company is not None:
        effective = _apply_resolved_company_llm(base, resolved_company)
        return EffectiveLLMConfig(
            config=effective,
            capability=capability,
            cost_origin=resolved_company.cost_origin,
            billing_resource_name=(
                resolved_company.billing_resource_name
                if resolved_company.cost_origin == COST_ORIGIN_COMPANY
                else _fallback_models_billing_resource(effective.fallback_models)
            ),
            source="company_capability",
        )

    _reject_node_fallbacks(node_config, base)
    _validate_explicit_primary(node_config, base, capability)

    if base.provider and base.provider.startswith(CUSTOM_PROVIDER_REF_PREFIX):
        resolved_custom = resolve_custom_llm_provider_ref(
            base.provider,
            capability=capability,
            model=base.model,
        )
        return EffectiveLLMConfig(
            config=_apply_resolved_custom_llm(base, resolved_custom),
            capability=capability,
            cost_origin=resolved_custom.cost_origin,
            billing_resource_name=resolved_custom.billing_resource_name,
            source="flow_custom_provider_ref",
        )

    return EffectiveLLMConfig(
        config=base,
        capability=capability,
        cost_origin=COST_ORIGIN_PLATFORM,
        billing_resource_name=None,
        source="flow_explicit_primary",
    )


__all__ = [
    "EffectiveLLMConfig",
    "llm_capability_from_node_config",
    "resolve_effective_llm_config_for_node",
]
