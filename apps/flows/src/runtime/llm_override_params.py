"""Параметры вызова LLM из NodeLLMConfig для get_llm / LLMClient.stream."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.flows.src.models.node_config import NodeLLMConfig
from core.clients.llm.config import LLMCallConfig
from core.variables import VariableResolutionError, VarResolver

if TYPE_CHECKING:
    from core.state import ExecutionState


def split_llm_config_for_client(
    config: NodeLLMConfig | None,
) -> tuple[
    str | None,
    float | None,
    str | None,
    str | None,
    str | None,
    int | None,
    str | None,
    list[LLMCallConfig] | None,
]:
    """Поля для get_llm / get_llm_for_state."""
    if not config:
        return None, None, None, None, None, None, None, None
    return (
        config.model,
        config.temperature,
        config.provider,
        config.api_key,
        config.base_url,
        config.max_tokens,
        config.folder_id,
        config.fallback_models,
    )


def stream_kwargs_from_llm_config(config: NodeLLMConfig | None) -> dict[str, Any]:
    """
    Именованные аргументы для LLMClient.stream (и MockLLM.stream игнорирует лишнее).

    extra_request_body мержится в HTTP body последним в LLMClient.stream.
    """
    if not config:
        return {}
    out: dict[str, Any] = {}
    if config.top_p is not None:
        out["top_p"] = config.top_p
    if config.top_k is not None:
        out["top_k"] = config.top_k
    if config.frequency_penalty is not None:
        out["frequency_penalty"] = config.frequency_penalty
    if config.presence_penalty is not None:
        out["presence_penalty"] = config.presence_penalty
    if config.seed is not None:
        out["seed"] = config.seed
    if config.reasoning_effort is not None:
        out["reasoning_effort"] = config.reasoning_effort
    if config.extra_request_body:
        out["extra_body"] = dict(config.extra_request_body)
    return out


def client_kwargs_from_llm_config(
    config: NodeLLMConfig | None,
    state: ExecutionState | None,
) -> dict[str, Any]:
    """Arguments for get_llm/get_llm_for_state from the full LLM config."""
    if not config:
        return {}
    out: dict[str, Any] = {
        "model_name": config.model,
        "temperature": config.temperature,
        "provider": config.provider,
        "api_key": config.api_key,
        "base_url": config.base_url,
        "folder_id": config.folder_id,
        "max_tokens": config.max_tokens,
        "fallback_models": config.fallback_models,
        "top_p": config.top_p,
        "top_k": config.top_k,
        "frequency_penalty": config.frequency_penalty,
        "presence_penalty": config.presence_penalty,
        "seed": config.seed,
        "reasoning_effort": config.reasoning_effort,
        "extra_request_body": config.extra_request_body,
    }
    if config.extra_request_headers:
        out["extra_request_headers"] = {
            k: _resolve_str_var(v, state) for k, v in config.extra_request_headers.items()
        }
    return out


def _resolve_str_var(value: str, state: ExecutionState | None) -> str:
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


def resolve_llm_config_stream_kwargs(
    config: NodeLLMConfig | None,
    state: ExecutionState | None,
) -> dict[str, Any]:
    """
    stream_kwargs_from_llm_config + резолв @var: в extra_request_headers.
    extra_headers мержится в LLMClient последним (перекрывает Authorization и default_headers).
    """
    kw = stream_kwargs_from_llm_config(config)
    if not config or not config.extra_request_headers:
        return kw
    hdrs: dict[str, str] = {}
    for k, v in config.extra_request_headers.items():
        hdrs[k] = _resolve_str_var(v, state)
    out = dict(kw)
    out["extra_headers"] = hdrs
    return out


# Backward-compatible import aliases for older tests/modules.
split_llm_override_for_client = split_llm_config_for_client
stream_kwargs_from_override = stream_kwargs_from_llm_config
client_kwargs_from_override = client_kwargs_from_llm_config
resolve_override_stream_kwargs = resolve_llm_config_stream_kwargs
