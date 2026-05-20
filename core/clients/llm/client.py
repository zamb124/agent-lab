"""OpenAI-compatible HTTP LLM client."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Type,
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
from core.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)
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
        base_url: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout: float = 120.0,
        llm_provider: Optional[str] = None,
        candidates: Optional[List[LLMCallConfig]] = None,
        candidate_resolver: Optional[Callable[[], Awaitable[List[LLMCallConfig]]]] = None,
        first_token_timeout: Optional[float] = None,
        candidate_cooldown_seconds: float = 0.0,
        platform_default_free_pool: bool = False,
        platform_paid_fallback_enabled: bool = True,
        llm_source: Optional[str] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        extra_request_body: Optional[Dict[str, Any]] = None,
        extra_request_headers: Optional[Dict[str, str]] = None,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.top_k = top_k
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.seed = seed
        self.reasoning_effort: Optional[ReasoningEffort] = reasoning_effort
        self.extra_request_body = dict(extra_request_body) if extra_request_body else None
        self.extra_request_headers = dict(extra_request_headers) if extra_request_headers else None
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.llm_provider = (
            llm_provider if llm_provider is not None else _detect_provider(self.base_url)
        )
        self.llm_source = llm_source or "explicit"
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
            default_headers=dict(self.default_headers),
            source=self.llm_source,
        )
        self._static_candidates = list(candidates) if candidates is not None else [base_candidate]
        self._candidate_resolver = candidate_resolver
        self.first_token_timeout = first_token_timeout or 20.0
        self.candidate_cooldown_seconds = candidate_cooldown_seconds
        self.platform_default_free_pool = platform_default_free_pool
        self.platform_paid_fallback_enabled = platform_paid_fallback_enabled

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
            }
        )

    async def _resolve_candidates(
        self,
        *,
        openai_messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        response_format: Optional[Dict[str, Any]],
        model_override: Optional[str] = None,
    ) -> List[LLMCallConfig]:
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
                "LLM default free-pool: нет доступных моделей, совместимых с параметрами "
                "запроса (tools/response_format/files) и не находящихся в cooldown; "
                "платный fallback недоступен или тоже несовместим"
            )
        if (
            not candidates
            and self.platform_default_free_pool
            and not self.platform_paid_fallback_enabled
        ):
            raise RuntimeError(
                "LLM default free-pool: нет доступных бесплатных моделей в Redis; "
                "платный fallback отключён из-за неположительного баланса компании"
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
        base: Optional[Dict[str, Any]],
        overlay: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not base and not overlay:
            return None
        merged: Dict[str, Any] = {}
        if base:
            merged.update(base)
        if overlay:
            merged.update(overlay)
        return merged

    async def stream(
        self,
        messages: MessageInput,
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        stream_cancel_poll: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream-first LLM call with universal candidate fallback.

        Fallback is only allowed before the first event is yielded to callers.
        Once any chunk/status has been emitted, the response belongs to that
        concrete model and failures propagate normally.

        ``model`` is a per-call override: it uses this client's provider,
        credentials and base URL without mutating ``self.model``.
        """
        normalized_messages = _normalize_messages(messages)
        openai_messages = _messages_to_openai(normalized_messages)
        candidates = await self._resolve_candidates(
            openai_messages=openai_messages,
            tools=tools,
            response_format=response_format,
            model_override=model,
        )
        last_error: BaseException | None = None
        for candidate_index, candidate in enumerate(candidates):
            attempt = self._client_for_candidate(candidate)
            merged_extra_body = self._merge_optional_dicts(
                candidate.extra_request_body,
                extra_body,
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
                        yield event
                    else:
                        yield await agen.__anext__()
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
            except (LLMStreamIdleTimeoutError, httpx.HTTPError, OSError, json.JSONDecodeError) as exc:
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
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        stream_cancel_poll: Optional[Callable[[], Awaitable[bool]]] = None,
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
        messages: List[Message],
        json_output: bool = False,
        max_tokens: Optional[int] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str | Dict[str, Any]:
        openai_messages = _messages_to_openai(messages)
        candidates = await self._resolve_candidates(
            openai_messages=openai_messages,
            tools=None,
            response_format={"type": "json_object"} if json_output else None,
        )
        last_error: BaseException | None = None
        for candidate_index, candidate in enumerate(candidates):
            attempt = self._client_for_candidate(candidate)
            try:
                return await attempt._invoke_once(
                    messages,
                    json_output=json_output,
                    max_tokens=max_tokens,
                    extra_body=extra_body,
                    extra_headers=extra_headers,
                )
            except (httpx.HTTPError, OSError, json.JSONDecodeError) as exc:
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
        messages: List[Message],
        json_output: bool = False,
        max_tokens: Optional[int] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str | Dict[str, Any]:
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
        response_model: Type[T],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> T: ...

    @overload
    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: None = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Message: ...

    async def chat(
        self,
        messages: MessageInput,
        *,
        response_model: Optional[Type[T]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        max_tokens: Optional[int] = None,
        frequency_penalty: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        seed: Optional[int] = None,
        reasoning_effort: Optional[ReasoningEffort] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Message | T:
        """
        Единый метод вызова LLM.

        Принимает messages в любом формате и возвращает:
        - T (экземпляр Pydantic модели) если указан response_model
        - Message с tool_calls если указаны tools (и нет response_model)
        - Message с текстом в остальных случаях

        Args:
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

        Returns:
            Message или экземпляр response_model

        Examples:
            # Простой чат
            msg = await llm.chat("Привет!")

            # С параметрами
            msg = await llm.chat("Расскажи историю", temperature=0.9, max_tokens=500)

            # Structured output
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

        response_format = None
        if response_model:
            json_schema = response_model.model_json_schema()
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "strict": True,
                    "schema": json_schema,
                },
            }

        content_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
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
                    metadata_tool_calls = event.status.message.metadata.get("tool_calls")
                    if metadata_tool_calls:
                        tool_calls = metadata_tool_calls

        content = "".join(content_parts)
        if response_model:
            text_for_json = content if content.strip() else last_status_text
            if not text_for_json.strip():
                raise ValueError(
                    "LLM structured output: пустой ответ (нет текста вне reasoning-артефакта "
                    "и нет текста в финальном статусе задачи)"
                )
            structured_payload = json.loads(text_for_json)
            return response_model.model_validate(structured_payload)

        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )


__all__ = ["LLMClient"]
