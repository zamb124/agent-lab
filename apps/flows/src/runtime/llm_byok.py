"""
BYOK (Bring Your Own Key / endpoint): детекция для биллинга и pre-flight баланса.
"""

from __future__ import annotations

from apps.flows.src.models.node_config import NodeLLMConfig


def is_llm_byok_config(config: NodeLLMConfig | None) -> bool:
    """True если в LLM config заданы свой api_key, свой base_url или provider=custom_openai_compatible.

    Канонический источник правды для cost_origin — ``core.ai.models.ResolvedAIModel.cost_origin``,
    но раннер использует эту эвристику как быстрый проверочный путь по конфигу ноды.
    """
    if not config:
        return False
    if config.api_key is not None and str(config.api_key).strip():
        return True
    if config.base_url is not None and str(config.base_url).strip():
        return True
    if config.provider == "custom_openai_compatible":
        return True
    return False


is_llm_byok_override = is_llm_byok_config


def is_llm_byok_resource(
    *, api_key: str | None, base_url: str | None, provider: str | None = None
) -> bool:
    if api_key is not None and str(api_key).strip():
        return True
    if base_url is not None and str(base_url).strip():
        return True
    if provider == "custom_openai_compatible":
        return True
    return False
