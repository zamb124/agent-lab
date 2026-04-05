"""
Параметры вызова LLM из NodeLLMOverride для get_llm / LLMClient.stream.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from apps.flows.src.models.node_config import NodeLLMOverride


def split_llm_override_for_client(
    override: Optional[NodeLLMOverride],
) -> Tuple[
    Optional[str],
    Optional[float],
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[int],
]:
    """Поля для get_llm / get_llm_for_state."""
    if not override:
        return None, None, None, None, None, None
    return (
        override.model,
        override.temperature,
        override.provider,
        override.api_key,
        override.base_url,
        override.max_tokens,
    )


def stream_kwargs_from_override(override: Optional[NodeLLMOverride]) -> Dict[str, Any]:
    """
    Именованные аргументы для LLMClient.stream (и MockLLM.stream игнорирует лишнее).

    extra_request_body мержится в HTTP body последним в LLMClient.stream.
    """
    if not override:
        return {}
    out: Dict[str, Any] = {}
    if override.top_p is not None:
        out["top_p"] = override.top_p
    if override.top_k is not None:
        out["top_k"] = override.top_k
    if override.frequency_penalty is not None:
        out["frequency_penalty"] = override.frequency_penalty
    if override.presence_penalty is not None:
        out["presence_penalty"] = override.presence_penalty
    if override.seed is not None:
        out["seed"] = override.seed
    if override.reasoning_effort is not None:
        out["reasoning_effort"] = override.reasoning_effort
    if override.extra_request_body:
        out["extra_body"] = dict(override.extra_request_body)
    return out
