"""
Параметры вызова LLM из NodeLLMOverride для get_llm / LLMClient.stream.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from apps.flows.src.models.node_config import NodeLLMOverride
from core.clients.llm.config import LLMCallConfig
from core.variables import VariableResolutionError, VarResolver

if TYPE_CHECKING:
    from core.state import ExecutionState


def split_llm_override_for_client(
    override: Optional[NodeLLMOverride],
) -> Tuple[
    Optional[str],
    Optional[float],
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[int],
    Optional[str],
    Optional[List[LLMCallConfig]],
]:
    """Поля для get_llm / get_llm_for_state."""
    if not override:
        return None, None, None, None, None, None, None, None
    return (
        override.model,
        override.temperature,
        override.provider,
        override.api_key,
        override.base_url,
        override.max_tokens,
        override.folder_id,
        override.fallback_models,
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


def client_kwargs_from_override(
    override: Optional[NodeLLMOverride],
    state: Optional["ExecutionState"],
) -> Dict[str, Any]:
    """Arguments for get_llm/get_llm_for_state from the full LLM config."""
    if not override:
        return {}
    out: Dict[str, Any] = {
        "model_name": override.model,
        "temperature": override.temperature,
        "provider": override.provider,
        "api_key": override.api_key,
        "base_url": override.base_url,
        "folder_id": override.folder_id,
        "max_tokens": override.max_tokens,
        "fallback_models": override.fallback_models,
        "top_p": override.top_p,
        "top_k": override.top_k,
        "frequency_penalty": override.frequency_penalty,
        "presence_penalty": override.presence_penalty,
        "seed": override.seed,
        "reasoning_effort": override.reasoning_effort,
        "extra_request_body": override.extra_request_body,
    }
    if override.extra_request_headers:
        out["extra_request_headers"] = {
            k: _resolve_str_var(v, state) for k, v in override.extra_request_headers.items()
        }
    return out


def _resolve_str_var(value: str, state: Optional["ExecutionState"]) -> str:
    if not value.startswith("@var:"):
        return value
    if state is None:
        raise VariableResolutionError(
            f"Нельзя резолвить '{value}' без ExecutionState (extra_request_headers)"
        )
    resolved = VarResolver.resolve_ref(value, state.variables or {})
    if not isinstance(resolved, str):
        raise VariableResolutionError(
            f"Переменная '{value}' для HTTP-заголовка должна резолвиться в строку"
        )
    if not resolved:
        raise VariableResolutionError(f"Переменная '{value}' резолвится в пустую строку")
    return resolved


def resolve_override_stream_kwargs(
    override: Optional[NodeLLMOverride],
    state: Optional["ExecutionState"],
) -> Dict[str, Any]:
    """
    stream_kwargs_from_override + резолв @var: в extra_request_headers.
    extra_headers мержится в LLMClient последним (перекрывает Authorization и default_headers).
    """
    kw = stream_kwargs_from_override(override)
    if not override or not override.extra_request_headers:
        return kw
    hdrs: Dict[str, str] = {}
    for k, v in override.extra_request_headers.items():
        hdrs[k] = _resolve_str_var(v, state)
    out = dict(kw)
    out["extra_headers"] = hdrs
    return out
