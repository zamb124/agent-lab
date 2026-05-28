"""HTTP LLM-клиент, совместимый с OpenAI."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
from typing import (
    TypeVar,
    overload,
)

import httpx
from a2a.types import (
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.message import get_message_text
from pydantic import BaseModel

from core.clients.llm.candidates import (
    candidate_key as _candidate_key,
)
from core.clients.llm.candidates import (
    candidate_supports_request as _candidate_supports_request,
)
from core.clients.llm.config import LLMCallConfig, ReasoningEffort
from core.clients.llm.context_layer import (
    LLMContextInput,
    llm_context_trace_metadata,
    merge_provider_cache_hints,
    prepare_messages_for_context_layer,
)
from core.clients.llm.errors import (
    LLMStreamIdleTimeoutError,
)
from core.clients.llm.messages import (
    MessageInput,
    StreamEvent,
)
from core.clients.llm.messages import (
    messages_have_non_text_parts as _messages_have_non_text_parts,
)
from core.clients.llm.messages import (
    messages_to_openai as _messages_to_openai,
)
from core.clients.llm.messages import (
    normalize_messages as _normalize_messages,
)
from core.clients.llm.provider_resolution import _detect_provider
from core.clients.llm.transport import (
    invoke_once as _transport_invoke_once,
)
from core.clients.llm.transport import (
    stream_once as _transport_stream_once,
)
from core.llm_context import CompiledLLMContext, LLMContextBlock, LLMContextSourceRegistry
from core.logging import get_logger
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_value,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
V = TypeVar("V")
_CANDIDATE_COOLDOWN_UNTIL: dict[str, float] = {}


class LLMClient:
    """
    LLM клиент через HTTP.
    Работает с A2A типами.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        default_headers: dict[str, str] | None = None,
        timeout: float = 120.0,
        llm_provider: str | None = None,
        candidates: list[LLMCallConfig] | None = None,
        candidate_resolver: Callable[[], Awaitable[list[LLMCallConfig]]] | None = None,
        first_token_timeout: float | None = None,
        candidate_cooldown_seconds: float = 0.0,
        platform_default_free_pool: bool = False,
        platform_paid_fallback_enabled: bool = True,
        llm_source: str | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        extra_request_body: JsonObject | None = None,
        extra_request_headers: dict[str, str] | None = None,
        context_length: int | None = None,
    ):
        self.model: str = model
        self.api_key: str = api_key
        self.base_url: str = base_url or "https://api.openai.com/v1"
        self.temperature: float = temperature
        self.max_tokens: int | None = max_tokens
        self.top_p: float | None = top_p
        self.top_k: int | None = top_k
        self.frequency_penalty: float | None = frequency_penalty
        self.presence_penalty: float | None = presence_penalty
        self.seed: int | None = seed
        self.reasoning_effort: ReasoningEffort | None = reasoning_effort
        self.extra_request_body: JsonObject | None = (
            dict(extra_request_body) if extra_request_body else None
        )
        self.extra_request_headers: dict[str, str] | None = (
            dict(extra_request_headers) if extra_request_headers else None
        )
        self.context_length: int | None = context_length
        self.default_headers: dict[str, str] = default_headers or {}
        self.timeout: float = timeout
        self.llm_provider: str = llm_provider or _detect_provider(self.base_url) or "unknown"
        self.llm_source: str = llm_source or "explicit"
        base_candidate = LLMCallConfig(
            provider=self.llm_provider or "unknown",
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=top_p,
            top_k=top_k,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            seed=seed,
            reasoning_effort=reasoning_effort,
            extra_request_body=dict(extra_request_body) if extra_request_body else None,
            extra_request_headers=dict(extra_request_headers) if extra_request_headers else None,
            context_length=context_length,
            default_headers=dict(self.default_headers),
            source=self.llm_source,
        )
        self._static_candidates: list[LLMCallConfig] = (
            list(candidates) if candidates is not None else [base_candidate]
        )
        self._candidate_resolver: Callable[[], Awaitable[list[LLMCallConfig]]] | None = (
            candidate_resolver
        )
        self.first_token_timeout: float = first_token_timeout or 20.0
        self.candidate_cooldown_seconds: float = candidate_cooldown_seconds
        self.platform_default_free_pool: bool = platform_default_free_pool
        self.platform_paid_fallback_enabled: bool = platform_paid_fallback_enabled

    def _client_for_candidate(self, candidate: LLMCallConfig) -> "LLMClient":
        if not candidate.model or not candidate.api_key:
            raise ValueError("resolved LLM config requires model and api_key")
        return LLMClient(
            model=str(candidate.model),
            api_key=str(candidate.api_key),
            base_url=candidate.base_url,
            temperature=candidate.temperature if candidate.temperature is not None else self.temperature,
            max_tokens=candidate.max_tokens if candidate.max_tokens is not None else self.max_tokens,
            default_headers=dict(candidate.default_headers),
            timeout=self.timeout,
            llm_provider=candidate.provider,
            candidates=[candidate],
            first_token_timeout=self.first_token_timeout,
            candidate_cooldown_seconds=self.candidate_cooldown_seconds,
            platform_default_free_pool=self.platform_default_free_pool,
            platform_paid_fallback_enabled=self.platform_paid_fallback_enabled,
            llm_source=candidate.source,
            top_p=candidate.top_p,
            top_k=candidate.top_k,
            frequency_penalty=candidate.frequency_penalty,
            presence_penalty=candidate.presence_penalty,
            seed=candidate.seed,
            reasoning_effort=candidate.reasoning_effort,
            extra_request_body=candidate.extra_request_body,
            extra_request_headers=candidate.extra_request_headers,
            context_length=candidate.context_length,
        )

    def _candidate_with_client_defaults(self, candidate: LLMCallConfig) -> LLMCallConfig:
        return candidate.model_copy(
            update={
                "temperature": (
                    candidate.temperature
                    if candidate.temperature is not None
                    else self.temperature
                ),
                "max_tokens": (
                    candidate.max_tokens
                    if candidate.max_tokens is not None
                    else self.max_tokens
                ),
                "top_p": candidate.top_p if candidate.top_p is not None else self.top_p,
                "top_k": candidate.top_k if candidate.top_k is not None else self.top_k,
                "frequency_penalty": (
                    candidate.frequency_penalty
                    if candidate.frequency_penalty is not None
                    else self.frequency_penalty
                ),
                "presence_penalty": (
                    candidate.presence_penalty
                    if candidate.presence_penalty is not None
                    else self.presence_penalty
                ),
                "seed": candidate.seed if candidate.seed is not None else self.seed,
                "reasoning_effort": (
                    candidate.reasoning_effort
                    if candidate.reasoning_effort is not None
                    else self.reasoning_effort
                ),
                "extra_request_body": (
                    candidate.extra_request_body
                    if candidate.extra_request_body is not None
                    else self.extra_request_body
                ),
                "extra_request_headers": (
                    candidate.extra_request_headers
                    if candidate.extra_request_headers is not None
                    else self.extra_request_headers
                ),
                "context_length": (
                    candidate.context_length
                    if candidate.context_length is not None
                    else self.context_length
                ),
            }
        )

    async def _resolve_candidates(
        self,
        *,
        openai_messages: list[JsonObject],
        tools: list[JsonObject] | None,
        response_format: JsonObject | None,
        model_override: str | None = None,
    ) -> list[LLMCallConfig]:
        if model_override is not None:
            model = model_override.strip()
            if not model:
                raise ValueError("LLM model override must be a non-empty string")
            candidates = [
                LLMCallConfig(
                    provider=self.llm_provider or "unknown",
                    model=model,
                    api_key=self.api_key,
                    base_url=self.base_url,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    top_p=self.top_p,
                    top_k=self.top_k,
                    frequency_penalty=self.frequency_penalty,
                    presence_penalty=self.presence_penalty,
                    seed=self.seed,
                    reasoning_effort=self.reasoning_effort,
                    extra_request_body=dict(self.extra_request_body)
                    if self.extra_request_body
                    else None,
                    extra_request_headers=dict(self.extra_request_headers)
                    if self.extra_request_headers
                    else None,
                    context_length=self.context_length,
                    default_headers=dict(self.default_headers),
                    source=self.llm_source,
                )
            ]
        else:
            candidates = list(self._static_candidates)
        if model_override is None and self._candidate_resolver is not None:
            resolved_candidates = await self._candidate_resolver()
            if resolved_candidates:
                candidates = [
                    self._candidate_with_client_defaults(candidate)
                    for candidate in resolved_candidates
                ]

        has_files = _messages_have_non_text_parts(openai_messages)
        has_tools = bool(tools)
        has_response_format = bool(response_format)
        current_time = time.monotonic()
        filtered_candidates: list[LLMCallConfig] = []
        seen_candidate_keys: set[str] = set()
        for candidate in candidates:
            candidate_cache_key = _candidate_key(candidate)
            if candidate_cache_key in seen_candidate_keys:
                continue
            seen_candidate_keys.add(candidate_cache_key)
            cooldown_until = _CANDIDATE_COOLDOWN_UNTIL.get(candidate_cache_key, 0.0)
            if cooldown_until > current_time:
                logger.info(
                    "llm.candidate_skipped_cooldown",
                    provider=candidate.provider,
                    model=candidate.model,
                    cooldown_left_seconds=round(cooldown_until - current_time, 1),
                )
                continue
            if not _candidate_supports_request(
                candidate,
                has_files=has_files,
                has_tools=has_tools,
                has_response_format=has_response_format,
            ):
                logger.info(
                    "llm.candidate_skipped_capability",
                    provider=candidate.provider,
                    model=candidate.model,
                    has_files=has_files,
                    has_tools=has_tools,
                    has_response_format=has_response_format,
                )
                continue
            filtered_candidates.append(candidate)
        if filtered_candidates:
            return filtered_candidates
        if self.platform_default_free_pool and candidates:
            raise RuntimeError(
                "LLM default free-pool: нет доступных моделей, совместимых с параметрами запроса "
                + "(tools/response_format/files) и не находящихся в cooldown; платный fallback "
                + "недоступен или тоже несовместим"
            )
        if (
            not candidates
            and self.platform_default_free_pool
            and not self.platform_paid_fallback_enabled
        ):
            raise RuntimeError(
                "LLM default free-pool: нет доступных бесплатных моделей в Redis; платный "
                + "fallback отключён из-за неположительного баланса компании"
            )
        return candidates[:1]

    def _cooldown_candidate(self, candidate: LLMCallConfig) -> None:
        if self.candidate_cooldown_seconds <= 0:
            return
        _CANDIDATE_COOLDOWN_UNTIL[_candidate_key(candidate)] = (
            time.monotonic() + self.candidate_cooldown_seconds
        )

    @staticmethod
    def _merge_optional_dicts(
        base: dict[str, V] | None,
        overlay: dict[str, V] | None,
    ) -> dict[str, V] | None:
        if not base and not overlay:
            return None
        merged: dict[str, V] = {}
        if base:
            merged.update(base)
        if overlay:
            merged.update(overlay)
        return merged

    async def stream(
        self,
        messages: MessageInput,
        tools: list[JsonObject] | None = None,
        response_format: JsonObject | None = None,
        model: str | None = None,
        task_id: str | None = None,
        context_id: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        llm_context: LLMContextInput | None = None,
        llm_context_blocks: list[LLMContextBlock] | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
        stream_cancel_poll: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream-first LLM-вызов с универсальным fallback по кандидатам.

        Fallback допустим только до первого события, отданного вызывающему коду.
        После любого chunk/status ответ принадлежит конкретной модели,
        и сбои пробрасываются как обычно.

        ``model`` — per-call override: использует provider, credentials
        и base URL этого клиента без изменения ``self.model``.
        """
        normalized_messages = _normalize_messages(messages)
        base_openai_messages = _messages_to_openai(normalized_messages)
        candidates = await self._resolve_candidates(
            openai_messages=base_openai_messages,
            tools=tools,
            response_format=response_format,
            model_override=model,
        )
        prepared_context = await prepare_messages_for_context_layer(
            normalized_messages,
            tools=tools,
            llm_context=llm_context,
            llm_context_blocks=llm_context_blocks,
            llm_context_source_registry=llm_context_source_registry,
            model_context_length=_strictest_context_length(candidates),
            output_token_reserve=_max_output_token_reserve(candidates, max_tokens),
        )
        normalized_messages = prepared_context.messages
        last_error: BaseException | None = None
        for candidate_index, candidate in enumerate(candidates):
            attempt = self._client_for_candidate(candidate)
            merged_extra_body = self._merge_optional_dicts(
                candidate.extra_request_body,
                extra_body,
            )
            merged_extra_body = merge_provider_cache_hints(
                provider=candidate.provider,
                model=candidate.model,
                extra_body=merged_extra_body,
                provider_hints=(
                    prepared_context.compiled_context.provider_hints
                    if prepared_context.compiled_context is not None
                    else None
                ),
            )
            merged_extra_headers = self._merge_optional_dicts(
                candidate.extra_request_headers,
                extra_headers,
            )
            yielded_any = False
            agen = attempt._stream_once(
                normalized_messages,
                tools=tools,
                response_format=response_format,
                task_id=task_id,
                context_id=context_id,
                temperature=temperature if temperature is not None else candidate.temperature,
                top_p=top_p if top_p is not None else candidate.top_p,
                top_k=top_k if top_k is not None else candidate.top_k,
                max_tokens=max_tokens if max_tokens is not None else candidate.max_tokens,
                frequency_penalty=(
                    frequency_penalty
                    if frequency_penalty is not None
                    else candidate.frequency_penalty
                ),
                presence_penalty=(
                    presence_penalty
                    if presence_penalty is not None
                    else candidate.presence_penalty
                ),
                seed=seed if seed is not None else candidate.seed,
                reasoning_effort=(
                    reasoning_effort
                    if reasoning_effort is not None
                    else candidate.reasoning_effort
                ),
                extra_body=merged_extra_body,
                extra_headers=merged_extra_headers,
                stream_cancel_poll=stream_cancel_poll,
            )
            try:
                while True:
                    if not yielded_any:
                        event = await asyncio.wait_for(
                            agen.__anext__(),
                            timeout=self.first_token_timeout,
                        )
                        yielded_any = True
                        if candidate_index > 0:
                            logger.info(
                                "llm.candidate_fallback_succeeded",
                                provider=candidate.provider,
                                model=candidate.model,
                                source=candidate.source,
                                attempt=candidate_index + 1,
                            )
                        yield _attach_llm_context_metadata(
                            event,
                            prepared_context.compiled_context,
                        )
                    else:
                        yield _attach_llm_context_metadata(
                            await agen.__anext__(),
                            prepared_context.compiled_context,
                        )
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError as exc:
                last_error = exc
                if yielded_any:
                    raise
                self._cooldown_candidate(candidate)
                with suppress(Exception):
                    await agen.aclose()
                logger.warning(
                    "llm.candidate_first_token_timeout",
                    provider=candidate.provider,
                    model=candidate.model,
                    source=candidate.source,
                    timeout_seconds=self.first_token_timeout,
                    attempt=candidate_index + 1,
                    remaining=len(candidates) - candidate_index - 1,
                )
                continue
            except (
                LLMStreamIdleTimeoutError,
                httpx.HTTPError,
                OSError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                last_error = exc
                if yielded_any:
                    raise
                self._cooldown_candidate(candidate)
                with suppress(Exception):
                    await agen.aclose()
                logger.warning(
                    "llm.candidate_failed_before_first_event",
                    provider=candidate.provider,
                    model=candidate.model,
                    source=candidate.source,
                    attempt=candidate_index + 1,
                    remaining=len(candidates) - candidate_index - 1,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM stream: нет доступных model candidates")

    async def _stream_once(
        self,
        messages: list[Message],
        tools: list[JsonObject] | None = None,
        response_format: JsonObject | None = None,
        task_id: str | None = None,
        context_id: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        stream_cancel_poll: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        async for event in _transport_stream_once(
            self,
            messages=messages,
            tools=tools,
            response_format=response_format,
            task_id=task_id,
            context_id=context_id,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            seed=seed,
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
            extra_headers=extra_headers,
            stream_cancel_poll=stream_cancel_poll,
        ):
            yield event

    async def invoke(
        self,
        messages: list[Message],
        json_output: bool = False,
        max_tokens: int | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        llm_context: LLMContextInput | None = None,
        llm_context_blocks: list[LLMContextBlock] | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
    ) -> str | JsonObject:
        base_openai_messages = _messages_to_openai(messages)
        candidates = await self._resolve_candidates(
            openai_messages=base_openai_messages,
            tools=None,
            response_format={"type": "json_object"} if json_output else None,
        )
        prepared_context = await prepare_messages_for_context_layer(
            messages,
            tools=None,
            llm_context=llm_context,
            llm_context_blocks=llm_context_blocks,
            llm_context_source_registry=llm_context_source_registry,
            model_context_length=_strictest_context_length(candidates),
            output_token_reserve=_max_output_token_reserve(candidates, max_tokens),
        )
        prepared_messages = prepared_context.messages
        last_error: BaseException | None = None
        for candidate_index, candidate in enumerate(candidates):
            attempt = self._client_for_candidate(candidate)
            merged_extra_body = self._merge_optional_dicts(
                candidate.extra_request_body,
                extra_body,
            )
            merged_extra_body = merge_provider_cache_hints(
                provider=candidate.provider,
                model=candidate.model,
                extra_body=merged_extra_body,
                provider_hints=(
                    prepared_context.compiled_context.provider_hints
                    if prepared_context.compiled_context is not None
                    else None
                ),
            )
            merged_extra_headers = self._merge_optional_dicts(
                candidate.extra_request_headers,
                extra_headers,
            )
            try:
                return await attempt._invoke_once(
                    prepared_messages,
                    json_output=json_output,
                    max_tokens=max_tokens,
                    extra_body=merged_extra_body,
                    extra_headers=merged_extra_headers,
                )
            except (httpx.HTTPError, OSError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                self._cooldown_candidate(candidate)
                logger.warning(
                    "llm.invoke_candidate_failed",
                    provider=candidate.provider,
                    model=candidate.model,
                    source=candidate.source,
                    attempt=candidate_index + 1,
                    remaining=len(candidates) - candidate_index - 1,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM invoke: нет доступных model candidates")

    async def _invoke_once(
        self,
        messages: list[Message],
        json_output: bool = False,
        max_tokens: int | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> str | JsonObject:
        return await _transport_invoke_once(
            self,
            messages=messages,
            json_output=json_output,
            max_tokens=max_tokens,
            extra_body=extra_body,
            extra_headers=extra_headers,
        )

    @overload
    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: type[T],
        tools: list[JsonObject] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        llm_context: LLMContextInput | None = None,
        llm_context_blocks: list[LLMContextBlock] | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
    ) -> T: ...

    @overload
    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: None = None,
        tools: list[JsonObject] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        llm_context: LLMContextInput | None = None,
        llm_context_blocks: list[LLMContextBlock] | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
    ) -> Message: ...

    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: type[T] | None = None,
        tools: list[JsonObject] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        max_tokens: int | None = None,
        frequency_penalty: float | None = None,
        presence_penalty: float | None = None,
        seed: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        llm_context: LLMContextInput | None = None,
        llm_context_blocks: list[LLMContextBlock] | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
    ) -> Message | T:
        """
        Единый метод вызова LLM.

        Принимает messages в любом формате и возвращает:
        - T (экземпляр Pydantic модели) если указан response_model
        - Message с tool_calls если указаны tools (и нет response_model)
        - Message с текстом в остальных случаях

        Аргументы:
            messages: Сообщения в любом формате:
                - str: "Привет!"
                - List[str]: ["Привет!", "Привет! Как дела?", "Отлично!"]
                - Message или List[Message]: A2A сообщения
                - Dict или List[Dict]: {"role": "user", "content": "..."}
            response_model: Pydantic модель для structured output
            tools: Список tools для function calling
            model: Имя модели (переопределяет self.model)
            temperature: Температура генерации (0.0-2.0)
            top_p: Top-P семплирование (0.0-1.0)
            top_k: Top-K семплирование
            max_tokens: Максимальное количество токенов
            frequency_penalty: Штраф за частоту токенов (-2.0-2.0)
            presence_penalty: Штраф за присутствие токенов (-2.0-2.0)
            llm_context: Inline patch профиля контекстного слоя
            llm_context_blocks: Уже извлеченные блоки памяти/RAG/tool summaries
            llm_context_source_registry: Registry backend-источников контекстных блоков

        Возвращает:
            Message или экземпляр response_model

        Примеры:
            # Простой чат
            msg = await llm.chat("Привет!")

            # С параметрами
            msg = await llm.chat("Расскажи историю", temperature=0.9, max_tokens=500)

            # Структурированный вывод
            class User(BaseModel):
                name: str
                age: int

            user = await llm.chat("Extract: John is 25", response_model=User)
            print(user.name, user.age)

            # Вызов функций
            msg = await llm.chat(messages, tools=[...])
            if msg.metadata and msg.metadata.get("tool_calls"):
                ...
        """
        normalized_messages = _normalize_messages(messages)

        response_format: JsonObject | None = None
        if response_model:
            json_schema = require_json_object(
                response_model.model_json_schema(),
                "llm.response_model.schema",
            )
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": json_schema,
                },
            }

        content_parts: list[str] = []
        tool_calls: JsonArray = []
        last_status_text = ""

        async for event in self.stream(
            normalized_messages,
            tools=tools if not response_model else None,
            response_format=response_format,
            model=model,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            seed=seed,
            reasoning_effort=reasoning_effort,
            extra_body=extra_body,
            extra_headers=extra_headers,
            llm_context=llm_context,
            llm_context_blocks=llm_context_blocks,
            llm_context_source_registry=llm_context_source_registry,
        ):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.artifact and event.artifact.name != "reasoning" and event.artifact.parts:
                    for part in event.artifact.parts:
                        root = part.root
                        if isinstance(root, TextPart):
                            content_parts.append(root.text)
            if isinstance(event, TaskStatusUpdateEvent) and event.status:
                if event.status.message:
                    status_text = get_message_text(event.status.message)
                    if status_text:
                        last_status_text = status_text
                if event.status.message and event.status.message.metadata:
                    metadata = require_json_object(
                        event.status.message.metadata,
                        "llm.status.message.metadata",
                    )
                    metadata_tool_calls = metadata.get("tool_calls")
                    if metadata_tool_calls:
                        tool_calls = require_json_array(
                            metadata_tool_calls,
                            "llm.status.message.metadata.tool_calls",
                        )

        content = "".join(content_parts)
        if response_model:
            text_for_json = content if content.strip() else last_status_text
            if not text_for_json.strip():
                raise ValueError(
                    "LLM structured output: пустой ответ (нет текста вне reasoning-артефакта и нет "
                    + "текста в финальном статусе задачи)"
                )
            structured_payload: JsonValue = parse_json_value(
                text_for_json,
                "llm.structured_output",
            )
            return response_model.model_validate(structured_payload)

        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )


def _strictest_context_length(candidates: list[LLMCallConfig]) -> int | None:
    lengths = [
        candidate.context_length
        for candidate in candidates
        if isinstance(candidate.context_length, int) and candidate.context_length > 0
    ]
    return min(lengths) if lengths else None


def _max_output_token_reserve(
    candidates: list[LLMCallConfig],
    max_tokens_override: int | None,
) -> int | None:
    token_limits: list[int] = []
    if isinstance(max_tokens_override, int) and max_tokens_override >= 0:
        token_limits.append(max_tokens_override)
    for candidate in candidates:
        if isinstance(candidate.max_tokens, int) and candidate.max_tokens >= 0:
            token_limits.append(candidate.max_tokens)
    return max(token_limits) if token_limits else None


def _attach_llm_context_metadata(
    event: StreamEvent,
    compiled_context: CompiledLLMContext | None,
) -> StreamEvent:
    metadata = llm_context_trace_metadata(compiled_context)
    if not metadata or not isinstance(event, TaskStatusUpdateEvent):
        return event
    if event.status.message is None:
        return event
    event_metadata = dict(event.status.message.metadata or {})
    event_metadata.setdefault("llm_context", metadata)
    event.status.message.metadata = event_metadata
    return event


__all__ = ["LLMClient"]
