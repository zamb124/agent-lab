"""
BYOK (Bring Your Own Key / endpoint): детекция для биллинга и pre-flight баланса.
"""

from __future__ import annotations

from typing import Optional

from apps.flows.src.models.node_config import NodeLLMOverride


def is_llm_byok_override(override: Optional[NodeLLMOverride]) -> bool:
    """True если в override заданы свой api_key и/или свой base_url."""
    if not override:
        return False
    if override.api_key is not None and str(override.api_key).strip():
        return True
    if override.base_url is not None and str(override.base_url).strip():
        return True
    return False


def is_llm_byok_resource(*, api_key: Optional[str], base_url: Optional[str]) -> bool:
    if api_key is not None and str(api_key).strip():
        return True
    if base_url is not None and str(base_url).strip():
        return True
    return False
