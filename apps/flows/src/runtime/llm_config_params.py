"""Параметры вызова LLM из NodeLLMConfig для billing и LLMClient.stream."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from apps.flows.src.models.node_config import NodeLLMConfig
from core.ai.llm_config import LLMCallConfig, ReasoningEffort
from core.types import JsonObject, require_json_object
from core.variables import VariableResolutionError, VarResolver

if TYPE_CHECKING:
    from core.state import ExecutionState


class LLMStreamKwargs(TypedDict, total=False):
    top_p: float
    top_k: int
    frequency_penalty: float
    presence_penalty: float
    seed: int
    reasoning_effort: ReasoningEffort
    extra_body: JsonObject
    extra_headers: dict[str, str]


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
    """Поля для billing/free-pool inspection."""
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


def stream_kwargs_from_llm_config(config: NodeLLMConfig | None) -> LLMStreamKwargs:
    """
    Именованные аргументы для LLMClient.stream.

    extra_request_body мержится в HTTP body последним в LLMClient.stream.
    """
    if not config:
        return {}
    out: LLMStreamKwargs = {}
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
        out["extra_body"] = require_json_object(
            config.extra_request_body,
            "llm.extra_request_body",
        )
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
) -> LLMStreamKwargs:
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
    kw["extra_headers"] = hdrs
    return kw
