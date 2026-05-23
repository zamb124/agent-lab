"""OpenAI-compatible HTTP transport for LLMClient."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import suppress
from typing import Any, cast

import httpx
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.message import new_agent_text_message

from core.clients.llm.errors import (
    INTER_CHUNK_WARN_SECONDS as _INTER_CHUNK_WARN_SECONDS,
)
from core.clients.llm.errors import (
    STREAM_IDLE_TIMEOUT_SECONDS,
    LLMStreamIdleTimeoutError,
    LLMStreamUserCancelledError,
)
from core.clients.llm.logging import log_llm_stream_response
from core.clients.llm.messages import LLMToolCall, LLMToolCallFunction, StreamEvent
from core.clients.llm.messages import messages_to_openai as _messages_to_openai
from core.clients.llm.openai_compat import (
    masked_headers as _masked_headers,
)
from core.clients.llm.openai_compat import (
    merge_openai_compatible_usage_into_usage_data as _merge_openai_compatible_usage_into_usage_data,
)
from core.clients.llm.openai_compat import (
    pretty_json as _pretty_json,
)
from core.http.client import ProxyStrategy, get_httpx_client
from core.http.egress_route_preference import (
    egress_prefer_proxy_set,
    normalized_http_origin,
)
from core.logging import get_logger
from core.types import JsonValue, require_json_object
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


async def stream_once(
    client: Any,
    messages: list[Message],
    tools: list[dict[str, Any]] | None = None,
    response_format: dict[str, Any] | None = None,
    task_id: str | None = None,
    context_id: str | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    max_tokens: int | None = None,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
    seed: int | None = None,
    reasoning_effort: str | None = None,
    extra_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
    stream_cancel_poll: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    """
    Stream-first метод вызова LLM.

    Принимает A2A Message, возвращает A2A события.

    Args:
        messages: Список сообщений
        tools: Список tools для function calling
        response_format: Формат ответа (json_schema для structured output)
        task_id: ID задачи
        context_id: ID контекста
        temperature: Температура генерации (переопределяет client.temperature)
        top_p: Top-P семплирование (nucleus sampling)
        top_k: Top-K семплирование
        max_tokens: Максимальное количество токенов (переопределяет client.max_tokens)
        frequency_penalty: Штраф за частоту токенов
        presence_penalty: Штраф за присутствие токенов
        seed: Seed для детерминизма
        reasoning_effort: Усилие reasoning (OpenAI-совместимые API)
        extra_body: Доп. поля JSON-тела; мержатся последними (перекрывают остальное)
        extra_headers: Доп. HTTP заголовки; мерж последним (перекрывают Authorization и default_headers)
    """
    task_id = task_id or str(uuid.uuid4())
    context_id = context_id or task_id

    openai_messages = _messages_to_openai(messages)

    headers: dict[str, str] = {
        "Authorization": f"Bearer {client.api_key}",
        "Content-Type": "application/json",
    }
    headers.update(client.default_headers)
    if extra_headers:
        headers.update(extra_headers)

    request_temperature = temperature if temperature is not None else client.temperature
    request_max_tokens = max_tokens if max_tokens is not None else client.max_tokens

    body: dict[str, Any] = {
        "model": client.model,
        "messages": openai_messages,
        "temperature": request_temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    if request_max_tokens:
        body["max_tokens"] = request_max_tokens

    if top_p is not None:
        body["top_p"] = top_p

    if top_k is not None:
        body["top_k"] = top_k

    if frequency_penalty is not None:
        body["frequency_penalty"] = frequency_penalty

    if presence_penalty is not None:
        body["presence_penalty"] = presence_penalty

    if seed is not None:
        body["seed"] = seed

    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort

    if tools:
        body["tools"] = tools

    if response_format:
        body["response_format"] = response_format

    if extra_body:
        for key, extra_body_value in extra_body.items():
            body[key] = extra_body_value

    logger.debug(
        "llm.request_prepared",
        messages_count=len(openai_messages),
        tools_count=len(tools) if tools else 0,
        has_response_format=bool(response_format),
    )
    logger.info(
        "llm.stream_request",
        llm_request=_pretty_json(
            {
                "url": f"{client.base_url}/chat/completions",
                "headers": _masked_headers(headers),
                "body": body,
            }
        ),
    )

    full_content = ""
    full_reasoning = ""
    tool_calls_buffer: dict[int, dict[str, Any]] = {}
    usage_data: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    stream_start_time = time.monotonic()

    async with get_httpx_client(timeout=client.timeout, strategy=ProxyStrategy.SMART) as http_client:
        try:
            async with http_client.stream(
                "POST", f"{client.base_url}/chat/completions", headers=headers, json=body
            ) as http_response:
                if http_response is None:
                    raise RuntimeError("LLM HTTP stream did not return a response")
                if http_response.status_code != 200:
                    # Для stream response пытаемся прочитать тело ошибки
                    error_text = f"HTTP {http_response.status_code}"
                    try:
                        # Читаем первые байты ответа для получения деталей ошибки
                        error_chunks = []
                        async for chunk in http_response.aiter_bytes():
                            error_chunks.append(chunk)
                            if len(b"".join(error_chunks)) > 2000:  # Ограничиваем размер
                                break
                        if error_chunks:
                            full_error = b"".join(error_chunks).decode("utf-8", errors="ignore")
                            # Пытаемся найти JSON в ответе
                            json_match = re.search(r"\{.*\}", full_error, re.DOTALL)
                            if json_match:
                                error_json = json.loads(json_match.group())
                                error_text = json.dumps(
                                    error_json, indent=2, ensure_ascii=False
                                )
                            else:
                                error_text = full_error[:1000]
                    except (httpx.HTTPError, OSError, UnicodeDecodeError) as exc:
                        logger.debug(
                            "llm.error_body_read_failed",
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )

                    logger.error(
                        "llm.api_error",
                        status_code=http_response.status_code,
                        error_text=error_text,
                        url=f"{client.base_url}/chat/completions",
                        model=client.model,
                        messages_count=len(openai_messages),
                    )
                    # Логируем первые и последние сообщения для отладки
                    if openai_messages:
                        logger.error(
                            "llm.api_error.first_message",
                            role=openai_messages[0].get("role"),
                            content_length=len(openai_messages[0].get("content", "")),
                        )
                        if len(openai_messages) > 1:
                            logger.error(
                                "llm.api_error.last_message",
                                role=openai_messages[-1].get("role"),
                                content_length=len(openai_messages[-1].get("content", "")),
                            )
                    http_response.raise_for_status()

                cancelled_evt = asyncio.Event()
                idle_timeout_evt = asyncio.Event()
                # Shared mutable: watchdog обновляет/читает last_chunk_time
                last_chunk_time = time.monotonic()
                chunks_received = 0
                idle_watch_task: asyncio.Task[None] | None = None

                async def _watch_idle_and_cancel() -> None:
                    """Watchdog: отмена по poll + idle timeout."""
                    nonlocal last_chunk_time
                    try:
                        while True:
                            await asyncio.sleep(1.0)
                            # 1. Проверяем отмену пользователем
                            if stream_cancel_poll is not None and await stream_cancel_poll():
                                cancelled_evt.set()
                                with suppress(Exception):
                                    await http_response.aclose()
                                return
                            # 2. Проверяем idle timeout
                            idle_seconds = time.monotonic() - last_chunk_time
                            idle_limit = (
                                client.first_token_timeout
                                if chunks_received == 0
                                else STREAM_IDLE_TIMEOUT_SECONDS
                            )
                            if idle_seconds >= idle_limit:
                                logger.error(
                                    "LLM stream idle timeout: %.1fs without data, "
                                    "chunks_received=%d, model=%s",
                                    idle_seconds,
                                    chunks_received,
                                    client.model,
                                )
                                idle_timeout_evt.set()
                                with suppress(Exception):
                                    await http_response.aclose()
                                return
                    except asyncio.CancelledError:
                        raise

                # Watchdog запускается ВСЕГДА (не только при stream_cancel_poll)
                idle_watch_task = run_with_log_context(
                    _watch_idle_and_cancel(),
                    name=f"llm.stream_idle_watch.{client.model}",
                    background_kind="llm_stream",
                )
                await asyncio.sleep(0)
                try:
                    try:
                        async for line in http_response.aiter_lines():
                            # Обновляем время последнего чанка для watchdog
                            current_time = time.monotonic()
                            inter_chunk_seconds = current_time - last_chunk_time
                            last_chunk_time = current_time
                            chunks_received += 1
                            if inter_chunk_seconds > _INTER_CHUNK_WARN_SECONDS:
                                logger.warning(
                                    "LLM stream slow chunk: %.1fs gap before chunk #%d, "
                                    "model=%s",
                                    inter_chunk_seconds,
                                    chunks_received,
                                    client.model,
                                )
                            if not line.startswith("data: "):
                                continue

                            sse_payload_text = line[6:]
                            if sse_payload_text == "[DONE]":
                                break

                            chunk = json.loads(sse_payload_text)

                            # Парсим usage из последнего chunk (stream_options: include_usage)
                            if chunk.get("usage"):
                                _merge_openai_compatible_usage_into_usage_data(
                                    chunk["usage"], usage_data
                                )

                            if not chunk.get("choices"):
                                continue

                            choice = chunk["choices"][0]
                            delta = choice.get("delta", {}) or {}

                            # Некоторые шлюзы отдают весь текст только в message.content финального чанка (delta пустой).
                            choice_message = choice.get("message")
                            if isinstance(choice_message, dict):
                                message_content = choice_message.get("content")
                                if (
                                    isinstance(message_content, str)
                                    and message_content
                                    and not delta.get("content")
                                    and not full_content
                                ):
                                    full_content = message_content
                                    yield TaskArtifactUpdateEvent(
                                        context_id=context_id,
                                        task_id=task_id,
                                        artifact=Artifact(
                                            artifact_id=str(uuid.uuid4()),
                                            parts=[Part(root=TextPart(text=message_content))],
                                        ),
                                        append=True,
                                        last_chunk=False,
                                    )

                            # Логируем delta для отладки reasoning (только если есть подозрительные поля)
                            if (
                                delta.get("reasoning")
                                or delta.get("reasoning_content")
                                or delta.get("type") == "reasoning"
                            ):
                                logger.debug("llm.reasoning_delta", delta=delta)

                            if delta.get("content"):
                                text = delta["content"]
                                full_content += text
                                yield TaskArtifactUpdateEvent(
                                    context_id=context_id,
                                    task_id=task_id,
                                    artifact=Artifact(
                                        artifact_id=str(uuid.uuid4()),
                                        parts=[Part(root=TextPart(text=text))],
                                    ),
                                    append=True,
                                    last_chunk=False,
                                )

                            # Обработка reasoning для моделей o1/o3
                            # Reasoning может приходить в разных форматах:
                            # - delta.reasoning (OpenAI o1/o3)
                            # - delta.reasoning_content (альтернативный формат)
                            # - delta.content с type="reasoning" (некоторые провайдеры)
                            # - choice.delta.reasoning (OpenRouter может использовать другой формат)
                            reasoning_text = None
                            if delta.get("reasoning"):
                                reasoning_text = delta["reasoning"]
                            elif delta.get("reasoning_content"):
                                reasoning_text = delta["reasoning_content"]
                            elif delta.get("type") == "reasoning" and delta.get("content"):
                                reasoning_text = delta["content"]
                            # Проверяем также в самом choice (для некоторых провайдеров)
                            if not reasoning_text and choice.get("delta", {}).get("reasoning"):
                                reasoning_text = choice["delta"]["reasoning"]

                            if reasoning_text:
                                full_reasoning += reasoning_text
                                logger.debug(
                                    "llm.reasoning_chunk",
                                    content_length=len(reasoning_text),
                                )
                                yield TaskArtifactUpdateEvent(
                                    context_id=context_id,
                                    task_id=task_id,
                                    artifact=Artifact(
                                        artifact_id=str(uuid.uuid4()),
                                        name="reasoning",
                                        parts=[Part(root=TextPart(text=reasoning_text))],
                                    ),
                                    append=True,
                                    last_chunk=False,
                                )

                            if delta.get("tool_calls"):
                                for tool_call_delta in delta["tool_calls"]:
                                    tool_call_index = tool_call_delta["index"]
                                    if tool_call_index not in tool_calls_buffer:
                                        tool_calls_buffer[tool_call_index] = {
                                            "id": tool_call_delta.get("id", ""),
                                            "name": "",
                                            "arguments": "",
                                        }
                                    if tool_call_delta.get("id"):
                                        tool_calls_buffer[tool_call_index]["id"] = tool_call_delta[
                                            "id"
                                        ]
                                    if tool_call_delta.get("function"):
                                        function_delta = tool_call_delta["function"]
                                        if function_delta.get("name"):
                                            tool_calls_buffer[tool_call_index]["name"] = (
                                                function_delta["name"]
                                            )
                                        if function_delta.get("arguments"):
                                            tool_calls_buffer[tool_call_index]["arguments"] += (
                                                function_delta["arguments"]
                                            )
                    except (
                        httpx.HTTPError,
                        OSError,
                        json.JSONDecodeError,
                    ) as exc:
                        if cancelled_evt.is_set():
                            raise LLMStreamUserCancelledError() from exc
                        if idle_timeout_evt.is_set():
                            # Учим SMART что этот origin надо через прокси:
                            # прямое соединение зависает mid-stream.
                            try:
                                origin = normalized_http_origin(
                                    f"{client.base_url}/chat/completions"
                                )
                                await egress_prefer_proxy_set(origin)
                                logger.info(
                                    "llm.stream_origin_marked_proxy_preferred",
                                    origin=origin,
                                    chunks_received=chunks_received,
                                )
                            except Exception as proxy_exc:
                                logger.warning(
                                    "llm.stream_origin_proxy_preference_failed",
                                    error=str(proxy_exc),
                                    error_type=type(proxy_exc).__name__,
                                )
                            raise LLMStreamIdleTimeoutError(
                                idle_seconds=(
                                    client.first_token_timeout
                                    if chunks_received == 0
                                    else STREAM_IDLE_TIMEOUT_SECONDS
                                ),
                                chunks_received=chunks_received,
                            ) from exc
                        raise
                finally:
                    if idle_watch_task is not None:
                        idle_watch_task.cancel()
                        with suppress(asyncio.CancelledError, RuntimeError):
                            await idle_watch_task
        except httpx.HTTPStatusError as exc:
            logger.error(
                "llm.api_http_error",
                error=str(exc),
                url=f"{client.base_url}/chat/completions",
                model=client.model,
            )
            raise

    if tool_calls_buffer:
        parsed_tool_calls: list[LLMToolCall] = []
        for tool_call_index in sorted(tool_calls_buffer.keys()):
            tool_call_buffer_entry = tool_calls_buffer[tool_call_index]
            try:
                parsed_arguments = (
                    cast(JsonValue, json.loads(tool_call_buffer_entry["arguments"]))
                    if tool_call_buffer_entry["arguments"]
                    else {}
                )
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "LLM tool call arguments must be valid JSON: "
                    f"{tool_call_buffer_entry['name']}"
                ) from exc
            tool_call_arguments = require_json_object(
                parsed_arguments,
                f"llm.tool_calls[{tool_call_index}].arguments",
            )
            parsed_tool_calls.append(
                LLMToolCall(
                    id=tool_call_buffer_entry["id"],
                    type="function",
                    function=LLMToolCallFunction(
                        name=tool_call_buffer_entry["name"],
                        arguments=tool_call_buffer_entry["arguments"],
                    ),
                    name=tool_call_buffer_entry["name"],
                    arguments=tool_call_arguments,
                )
            )

        message = Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=full_content))],
            metadata={
                "tool_calls": [
                    tool_call.model_dump(mode="json", exclude_none=True)
                    for tool_call in parsed_tool_calls
                ],
                "usage": usage_data,
                "model": client.model,
                "provider": client.llm_provider,
                "source": client.llm_source,
            },
        )
        yield TaskStatusUpdateEvent(
            context_id=context_id,
            task_id=task_id,
            status=TaskStatus(state=TaskState.working, message=message),
            final=False,
        )

    final_message = new_agent_text_message(full_content) if full_content else None
    if final_message:
        final_message.metadata = {
            "usage": usage_data,
            "model": client.model,
            "provider": client.llm_provider,
            "source": client.llm_source,
        }
    # final=False: это конец одного вызова LLM внутри задачи, не конец A2A-задачи.
    # completed+final=True рвёт EventSubscriber до node_complete и emit_complete канала.
    yield TaskStatusUpdateEvent(
        context_id=context_id,
        task_id=task_id,
        status=TaskStatus(
            state=TaskState.completed if not tool_calls_buffer else TaskState.working,
            message=final_message,
        ),
        final=False,
    )

    stream_duration = time.monotonic() - stream_start_time
    logger.info(
        "llm.stream_complete",
        provider=client.llm_provider,
        model=client.model,
        source=client.llm_source,
        chunks_count=chunks_received,
        content_length=len(full_content),
        reasoning_length=len(full_reasoning),
        tool_calls_count=len(tool_calls_buffer),
        duration_seconds=round(stream_duration, 1),
    )

    log_llm_stream_response(
        url=f"{client.base_url}/chat/completions",
        content=full_content,
        reasoning=full_reasoning if full_reasoning else None,
        tool_calls=list(tool_calls_buffer.values()) if tool_calls_buffer else None,
        usage=usage_data,
        provider=client.llm_provider,
        model=client.model,
        source=client.llm_source,
        duration_ms=stream_duration * 1000,
    )


async def invoke_once(
    client: Any,
    messages: list[Message],
    json_output: bool = False,
    max_tokens: int | None = None,
    extra_body: dict[str, Any] | None = None,
    extra_headers: dict[str, str] | None = None,
) -> str | dict[str, Any]:
    """
    Non-streaming вызов LLM.

    Удобен для vision/OCR запросов где не нужен streaming.

    Args:
        messages: Список A2A сообщений (может содержать FilePart)
        json_output: Запросить JSON формат ответа
        max_tokens: Максимальное количество токенов
        extra_body: Доп. поля JSON-тела; мержатся последними
        extra_headers: Доп. HTTP заголовки; мерж последним

    Returns:
        Строка или dict (при json_output=True)
    """
    openai_messages = _messages_to_openai(messages)

    headers: dict[str, str] = {
        "Authorization": f"Bearer {client.api_key}",
        "Content-Type": "application/json",
    }
    headers.update(client.default_headers)
    if extra_headers:
        headers.update(extra_headers)

    body: dict[str, Any] = {
        "model": client.model,
        "messages": openai_messages,
        "temperature": client.temperature,
        "max_tokens": max_tokens or client.max_tokens or 4096,
    }

    if json_output:
        body["response_format"] = {"type": "json_object"}

    if extra_body:
        for key, extra_body_value in extra_body.items():
            body[key] = extra_body_value

    logger.info(
        "llm.invoke_request_prepared",
        model=client.model,
        messages_count=len(openai_messages),
        json_output=json_output,
    )
    logger.info(
        "llm.invoke_request",
        llm_request=_pretty_json(
            {
                "url": f"{client.base_url}/chat/completions",
                "headers": _masked_headers(headers),
                "body": body,
            }
        ),
    )

    async with get_httpx_client(timeout=client.timeout, strategy=ProxyStrategy.SMART) as http_client:
        http_response = await http_client.post(
            f"{client.base_url}/chat/completions",
            headers=headers,
            json=body,
        )

        if http_response.status_code != 200:
            error_text = http_response.text[:1000]
            logger.error(
                "llm.invoke_error",
                status_code=http_response.status_code,
                error_text=error_text,
            )
            http_response.raise_for_status()

        response_payload = http_response.json()
        logger.info("llm.invoke_response", llm_response=_pretty_json(response_payload))

    content = response_payload["choices"][0]["message"]["content"]

    logger.info(
        "llm.invoke_complete",
        content_length=len(content) if content else 0,
    )

    if json_output and content:
        return json.loads(content)

    return content or ""


__all__ = ["invoke_once", "stream_once"]
