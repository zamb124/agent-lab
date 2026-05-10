"""
BYOK (Bring Your Own Key / endpoint): детекция для биллинга и pre-flight баланса.
"""

from __future__ import annotations

from typing import Optional

from apps.flows.src.models.node_config import NodeLLMOverride


def is_llm_byok_override(override: Optional[NodeLLMOverride]) -> bool:
    """True если в override заданы свой api_key, свой base_url или provider=custom_openai_compatible.

    Канонический источник правды для cost_origin — ``core.company_ai.resolver.ResolvedLLM.cost_origin``,
    но раннер использует эту эвристику как быстрый проверочный путь по конфигу ноды.
    """
    if not override:
        return False
    if override.api_key is not None and str(override.api_key).strip():
        return True
    if override.base_url is not None and str(override.base_url).strip():
        return True
    if override.provider == "custom_openai_compatible":
        return True
    return False


def is_llm_byok_resource(
    *, api_key: Optional[str], base_url: Optional[str], provider: Optional[str] = None
) -> bool:
    if api_key is not None and str(api_key).strip():
        return True
    if base_url is not None and str(base_url).strip():
        return True
    if provider == "custom_openai_compatible":
        return True
    return False
