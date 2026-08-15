"""
Mock LLM для тестов.
"""

import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TypeAlias, TypeVar, overload

from a2a.helpers.proto_helpers import get_message_text, new_text_message
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from pydantic import BaseModel

from core.a2a.codec import mapping_from_struct, part_has_raw, part_has_text, struct_from_mapping
from core.clients.llm.context_layer import (
    LLMContextInput,
    llm_context_trace_metadata,
    prepare_messages_for_context_layer,
)
from core.clients.llm.messages import (
    MessageInput,
    StreamEvent,
    build_a2a_message,
)
from core.clients.llm.messages import (
    normalize_messages as _normalize_messages,
)
from core.clients.llm.structured_output import resolve_structured_output_source_text
from core.clients.redis_client import RedisClient
from core.llm_context import LLMContextBlock, LLMContextSourceRegistry
from core.logging import get_logger
from core.test_scope import resolve_test_scope
from core.types import (
    JsonArray,
    JsonObject,
    parse_json_object,
    parse_json_value,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)
MockLLMQueuedResponse: TypeAlias = str | JsonObject


def mock_llm_responses_key(test_scope: str) -> str:
    """Ключ Redis очереди mock-ответов для конкретного test scope."""
    if not test_scope.strip():
        raise ValueError("mock_llm_responses_key: test_scope не должен быть пустым")
    return f"mock_llm:responses:{test_scope.strip()}"


def mock_llm_capture_key(test_scope: str) -> str:
    """Ключ Redis журнала вызовов MockLLM для конкретного test scope."""
    if not test_scope.strip():
        raise ValueError("mock_llm_capture_key: test_scope не должен быть пустым")
    return f"mock_llm:capture:{test_scope.strip()}"


_MOCK_STREAM_CHUNK_MAX = 256


def split_mock_stream_text(text: str) -> list[str]:
    """Чанки заранее известного mock-текста.

    Не 2–5 символов: каждый чанк — durable emit. Под ``-n10`` 3-символьные
    чанки + ``asyncio.sleep(0.005)`` держат ``llm_node`` ~80 с на одном
    CRM analyze (note-analyze остаётся ``running`` до poll 90 с).
    Минимум 2 чанка если длина > 1 — контракт stream-тестов.
    """
    if not text:
        return []
    if len(text) == 1:
        return [text]
    chunk_size = min(_MOCK_STREAM_CHUNK_MAX, max(1, (len(text) + 1) // 2))
    return [text[offset : offset + chunk_size] for offset in range(0, len(text), chunk_size)]


_global_mock_registry: dict[str, "MockLLM"] = {}

# Маркер «очередь была настроена, но исчерпана»: ключ с пустым массивом
# сохраняется, чтобы отличать исчерпание (ошибка теста) от отсутствия очереди
# (тест не использует Redis-мок — допустим паттерн/дефолтный ответ).
_MOCK_LLM_QUEUE_EXHAUSTED_MARKER = "__MOCK_LLM_QUEUE_EXHAUSTED__"

# Атомарно: один элемент JSON-массива за вызов (несколько async LLM на одном ключе).
_MOCK_LLM_REDIS_POP_SCRIPT = """
local raw_payload = redis.call('GET', KEYS[1])
if not raw_payload then
  return nil
end
local decoded = cjson.decode(raw_payload)
if decoded == nil or #decoded == 0 then
  return '__MOCK_LLM_QUEUE_EXHAUSTED__'
end
local head = table.remove(decoded, 1)
redis.call('SET', KEYS[1], cjson.encode(decoded), 'KEEPTTL')
return cjson.encode(head)
"""

# TTL очереди mock-ответов и журнала capture в Redis (test scope).
_MOCK_LLM_REDIS_TTL_SECONDS = 24 * 60 * 60


class MockLLM:
    """
    Mock LLM для тестов.
    Работает с A2A типами.

    Поддерживает Redis для межпроцессного обмена mock ответами:
    - Тест записывает ответы в Redis
    - Worker читает ответы из Redis
    """

    def __init__(self, model_name: str = "mock-gpt-4"):
        if not model_name.strip():
            raise ValueError("MockLLM model is required")
        self.model: str = model_name
        self.llm_provider: str = "mock"
        self._response_queue: list[MockLLMQueuedResponse] = []
        self._responses: dict[str, str] = {}
        self._tool_responses: dict[str, JsonObject] = {}
        self._default_response: str = "Mock LLM ответ"
        self._redis_client: RedisClient | None = None
        self._redis_key_override: str | None = None
        self._strict_redis_queue: bool = False

    def set_redis_client(self, redis_client: RedisClient) -> "MockLLM":
        """Устанавливает Redis клиент для межпроцессного обмена."""
        self._redis_client = redis_client
        return self

    def bind_redis_queue(
        self, redis_client: RedisClient, key: str, *, strict: bool = True
    ) -> "MockLLM":
        """
        Привязывает экземпляр к конкретной Redis-очереди ответов.

        Используется Mock Control System: каждая llm-нода читает строго свою
        очередь `mock_control:{session_id}:node:{node_id}` (или общую llm).
        При strict=True исчерпание очереди — ошибка (fail-closed), без
        тихого паттерн-фолбэка на дефолтный ответ.
        """
        self._redis_client = redis_client
        self._redis_key_override = key
        self._strict_redis_queue = strict
        return self

    def configure(
        self,
        response_queue: list[MockLLMQueuedResponse] | None = None,
        tool_responses: dict[str, JsonObject] | None = None,
        responses: dict[str, str] | None = None,
        default_response: str | None = None,
    ) -> "MockLLM":
        """Настройка mock ответов."""
        if response_queue is not None:
            self._response_queue = list(response_queue)
            logger.info("mock_llm.response_queue_configured", count=len(self._response_queue))

        if tool_responses:
            self._tool_responses = tool_responses

        if responses:
            self._responses = responses

        if default_response:
            self._default_response = default_response

        return self

    def reset(self) -> None:
        """Сброс всех настроек"""
        self._response_queue = []
        self._responses = {}
        self._tool_responses = {}
        self._default_response = "Mock LLM ответ"

    async def _get_redis_response(self) -> MockLLMQueuedResponse | None:
        """Получает ответ из Redis (межпроцессная очередь).

        При _redis_key_override (Mock Control System) читается строго заданный
        ключ. Иначе ключ выводится из test scope текущего запроса
        (`mock_llm:responses:<scope>`); без scope Redis-очередь не используется.
        """
        if not self._redis_client:
            return None

        if self._redis_key_override is not None:
            return await self._pop_single_redis_key(self._redis_key_override)

        test_scope = resolve_test_scope()
        if test_scope is None:
            return None
        return await self._pop_single_redis_key(mock_llm_responses_key(test_scope))

    async def _pop_single_redis_key(self, key: str) -> MockLLMQueuedResponse | None:
        """Атомарно снимает один элемент из Redis-ключа (Lua POP).

        None — очередь не настроена (ключа нет). Исчерпание настроенной
        очереди — ошибка (fail-closed): молчаливый паттерн-ответ маскировал бы
        недобор ответов в тесте.
        """
        if not self._redis_client:
            raise RuntimeError("_pop_single_redis_key вызван без Redis-клиента")
        try:
            redis_response_payload = await self._redis_client.eval(
                _MOCK_LLM_REDIS_POP_SCRIPT, 1, key
            )
            if redis_response_payload is None:
                return None
            if not isinstance(redis_response_payload, str):
                raise ValueError("mock_llm redis response must be a JSON string")
            if redis_response_payload == _MOCK_LLM_QUEUE_EXHAUSTED_MARKER:
                raise ValueError(f"MockLLM queue exhausted: {key}")
            redis_response = parse_json_value(redis_response_payload, "mock_llm.redis_response")
            if isinstance(redis_response, str):
                logger.info("mock_llm.redis_response_popped")
                return redis_response
            if isinstance(redis_response, dict):
                logger.info("mock_llm.redis_response_popped")
                return require_json_object(redis_response, "mock_llm.redis_response")
            raise ValueError("mock_llm redis response must be a string or JSON object")
        except Exception as exc:
            logger.warning(
                "mock_llm.redis_response_read_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

    async def _capture_call_to_redis(
        self,
        messages: list[Message],
        tools: list[JsonObject] | None,
        response_format: JsonObject | None,
        model: str | None = None,
        llm_context: JsonObject | None = None,
    ) -> None:
        """
        Пишет в журнал `mock_llm:capture:<test_scope>` запись об одном вызове
        MockLLM (`messages`, `tools`, `response_format`, `model`, optional
        `llm_context` trace metadata). Scope берётся из лог-контекста текущего
        запроса; вне test scope журнал не ведётся.

        `messages` нормализуются как plain text + role + metadata (ключи
        tool_calls / tool_call_id / system / usage). Part(raw=...) выписываются
        как `{"file": True, "mime_type": ...}` без bytes — журнал должен
        оставаться компактным даже для multimodal вызовов.
        """
        if not self._redis_client:
            return
        scope = resolve_test_scope()
        if scope is None:
            return

        normalized_messages = [
            _normalize_message_for_capture(message) for message in messages
        ]
        record: JsonObject = {
            "model": model or self.model,
            "messages": normalized_messages,
            "tools": tools or [],
            "response_format": response_format,
        }
        if llm_context is not None:
            record["llm_context"] = llm_context
        try:
            _ = await self._redis_client.rpush(
                mock_llm_capture_key(scope),
                json.dumps(record, ensure_ascii=False),
                ttl_seconds=_MOCK_LLM_REDIS_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                "mock_llm.capture_write_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

    def _get_response(self, messages: list[Message]) -> JsonObject:
        """Внутренний метод получения ответа."""
        # Сначала локальная очередь
        if self._response_queue:
            mock_response = self._response_queue.pop(0)
            logger.debug("mock_llm.local_response_popped", remaining=len(self._response_queue))
            return self._process_response(mock_response, messages)

        return self._generate_from_patterns(messages)

    async def _get_response_async(self, messages: list[Message]) -> JsonObject:
        """Асинхронный метод получения ответа с Redis поддержкой."""
        # Локальная очередь приоритетнее Redis: в одном тесте uvicorn ест очередь
        # из configure_mock_llm, а worker — из ключа mock_llm:responses без пересечения.
        if self._response_queue:
            mock_response = self._response_queue.pop(0)
            logger.debug("mock_llm.local_response_popped", remaining=len(self._response_queue))
            return self._process_response(mock_response, messages)

        redis_response = await self._get_redis_response()
        if redis_response is not None:
            return self._process_response(redis_response, messages)

        if self._redis_key_override is not None and self._strict_redis_queue:
            raise ValueError(
                f"MockLLM strict queue exhausted: {self._redis_key_override}"
            )

        return self._generate_from_patterns(messages)

    def _process_response(
        self,
        mock_response: MockLLMQueuedResponse,
        messages: list[Message],
    ) -> JsonObject:
        """Обрабатывает ответ из очереди"""
        if isinstance(mock_response, dict):
            if mock_response.get("type") == "tool_call":
                tool_name = mock_response.get("tool")
                if not isinstance(tool_name, str) or not tool_name:
                    raise ValueError("mock_llm tool_call.tool must be a non-empty string")
                arguments = require_json_object(
                    mock_response.get("args", {}),
                    "mock_llm.response.args",
                )
                raw_tool_call_id = mock_response.get("id")
                tool_call_id = (
                    raw_tool_call_id
                    if isinstance(raw_tool_call_id, str) and raw_tool_call_id
                    else f"call_mock_{tool_name}_{len(messages)}"
                )
                return {
                    "content": "",
                    "reasoning": None,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments),
                            },
                            "name": tool_name,
                            "arguments": arguments,
                        }
                    ],
                }
            elif mock_response.get("type") == "tool_calls":
                # Множественные tool_calls - ПАРАЛЛЕЛЬНОЕ выполнение
                calls = require_json_array(mock_response.get("calls", []), "mock_llm.response.calls")
                tool_calls: JsonArray = []
                for call_index, raw_call in enumerate(calls):
                    call = require_json_object(raw_call, "mock_llm.response.calls[]")
                    arguments = require_json_object(
                        call.get("args", {}),
                        "mock_llm.response.calls[].args",
                    )
                    tool_name = call.get("tool")
                    if not isinstance(tool_name, str) or not tool_name:
                        raise ValueError("mock_llm tool_calls[].tool must be a non-empty string")
                    raw_tool_call_id = call.get("id")
                    tool_call_id = (
                        raw_tool_call_id
                        if isinstance(raw_tool_call_id, str) and raw_tool_call_id
                        else f"call_mock_{tool_name}_{len(messages)}_{call_index}"
                    )
                    tool_calls.append({
                        "id": tool_call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(arguments)},
                        "name": tool_name,
                        "arguments": arguments,
                    })
                return {
                    "content": "",
                    "reasoning": None,
                    "tool_calls": tool_calls,
                }
            elif mock_response.get("type") == "text":
                content = mock_response.get("content", self._default_response)
                reasoning = mock_response.get("reasoning")
                return {
                    "content": content if isinstance(content, str) else self._default_response,
                    "reasoning": reasoning if isinstance(reasoning, str) else None,
                    "tool_calls": None,
                }
            elif mock_response.get("type") == "structured_output":
                # Структурированный вывод возвращает JSON как content
                structured_payload = mock_response.get("data", {})
                content = (
                    json.dumps(structured_payload, ensure_ascii=False)
                    if isinstance(structured_payload, dict)
                    else str(structured_payload)
                )
                reasoning = mock_response.get("reasoning")
                return {
                    "content": content,
                    "reasoning": reasoning if isinstance(reasoning, str) else None,
                    "tool_calls": None,
                }
            else:
                return {"content": str(mock_response), "reasoning": None, "tool_calls": None}
        return {"content": mock_response, "reasoning": None, "tool_calls": None}

    def _generate_from_patterns(self, messages: list[Message]) -> JsonObject:
        """Генерирует ответ на основе паттернов"""
        if not messages:
            return {"content": self._default_response, "reasoning": None, "tool_calls": None}

        last_message = messages[-1]
        content_str = get_message_text(last_message)
        metadata = (
            mapping_from_struct(last_message.metadata) if last_message.metadata else {}
        )
        if metadata and metadata.get("tool_call_id"):
            for key, mock_response_text in self._responses.items():
                if key.lower() in content_str.lower():
                    return {"content": mock_response_text, "reasoning": None, "tool_calls": None}
            return {"content": content_str or self._default_response, "reasoning": None, "tool_calls": None}

        for key, tool_config in self._tool_responses.items():
            if key.lower() in content_str.lower():
                arguments = require_json_object(
                    tool_config.get("args", {}),
                    "mock_llm.tool_responses.args",
                )
                tool_name = tool_config.get("tool")
                if not isinstance(tool_name, str) or not tool_name:
                    raise ValueError("mock_llm tool_responses[].tool must be a non-empty string")
                return {
                    "content": "",
                    "reasoning": None,
                    "tool_calls": [
                        {
                            "id": f"call_mock_{tool_name}_{len(messages)}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(arguments),
                            },
                            "name": tool_name,
                            "arguments": arguments,
                        }
                    ],
                }

        for key, mock_response_text in self._responses.items():
            if key.lower() in content_str.lower():
                return {"content": mock_response_text, "reasoning": None, "tool_calls": None}

        return {"content": self._default_response, "reasoning": None, "tool_calls": None}

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
        reasoning_effort: str | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        llm_context: LLMContextInput | None = None,
        llm_context_blocks: list[LLMContextBlock] | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
        stream_cancel_poll: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream метод — заранее известный mock-текст чанками (не 2–5 символов).

        Tool calls тоже стримятся по частям: сначала id, потом name, потом arguments кусками.

        Поддерживает Redis для межпроцессного обмена mock ответами.
        Поддерживает response_format для structured output.
        """
        del (
            temperature,
            top_p,
            top_k,
            max_tokens,
            frequency_penalty,
            presence_penalty,
            seed,
            reasoning_effort,
            extra_body,
            extra_headers,
            stream_cancel_poll,
        )

        task_id = task_id or str(uuid.uuid4())
        context_id = context_id or task_id
        artifact_id = str(uuid.uuid4())

        normalized_messages = _normalize_messages(messages)
        prepared_context = await prepare_messages_for_context_layer(
            normalized_messages,
            tools=tools,
            llm_context=llm_context,
            llm_context_blocks=llm_context_blocks,
            llm_context_source_registry=llm_context_source_registry,
        )
        normalized_messages = prepared_context.messages
        context_metadata = llm_context_trace_metadata(prepared_context.compiled_context)

        await self._capture_call_to_redis(
            messages=normalized_messages,
            tools=tools,
            response_format=response_format,
            model=model,
            llm_context=context_metadata,
        )

        # Используем async метод для поддержки Redis
        mock_response = await self._get_response_async(normalized_messages)
        content_raw = mock_response.get("content", "")
        content = content_raw if isinstance(content_raw, str) else ""
        reasoning_raw = mock_response.get("reasoning", "")
        reasoning = reasoning_raw if isinstance(reasoning_raw, str) else ""
        tool_calls_raw = mock_response.get("tool_calls")
        tool_calls = (
            require_json_array(tool_calls_raw, "mock_llm.response.tool_calls")
            if tool_calls_raw is not None
            else []
        )

        # Стримим reasoning чанками заранее известного текста (не по 3 символа).
        reasoning_artifact_id = str(uuid.uuid4())
        reasoning_chunks = split_mock_stream_text(reasoning)
        for reasoning_index, chunk in enumerate(reasoning_chunks):
            is_last_reasoning_chunk = reasoning_index == len(reasoning_chunks) - 1
            is_last_reasoning_overall = is_last_reasoning_chunk and not content and not tool_calls

            yield TaskArtifactUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                artifact=Artifact(
                    artifact_id=reasoning_artifact_id,
                    name="reasoning",
                    parts=[Part(text=chunk)],
                ),
                append=True,
                last_chunk=is_last_reasoning_overall,
            )

        # Стримим контент чанками заранее известного текста (не по 3 символа).
        content_chunks = split_mock_stream_text(content)
        for content_index, chunk in enumerate(content_chunks):
            is_last_content = content_index == len(content_chunks) - 1
            is_last = is_last_content and not tool_calls

            yield TaskArtifactUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                artifact=Artifact(
                    artifact_id=artifact_id,
                    name="response",
                    parts=[Part(text=chunk)],
                ),
                append=True,
                last_chunk=is_last,
            )

        # Tool calls: как в LLMClient.stream — сначала статус с tool_calls+usage, затем
        # второй статус (часто только usage), иначе LlmNodeRunner затирал бы tool_calls.
        if tool_calls:
            usage_data: JsonObject = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            message = build_a2a_message(
                role=Role.ROLE_AGENT,
                parts=[Part(text=content)],
                metadata={
                    "tool_calls": tool_calls,
                    "usage": usage_data,
                    **({"llm_context": context_metadata} if context_metadata else {}),
                },
            )
            yield TaskStatusUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                status=TaskStatus(state=TaskState.TASK_STATE_WORKING, message=message),
            )
            final_message = new_text_message(content, role=Role.ROLE_AGENT) if content else None
            if final_message is not None:
                final_message.metadata.CopyFrom(
                    struct_from_mapping(
                        {
                            "usage": usage_data,
                            **({"llm_context": context_metadata} if context_metadata else {}),
                        }
                    )
                )
            yield TaskStatusUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    message=final_message,
                ),
            )
        else:
            # WORKING: конец шага LLM, не конец A2A-задачи (см. transport.py).
            final_message = None
            if content:
                final_message = build_a2a_message(
                    role=Role.ROLE_AGENT,
                    parts=[Part(text=content)],
                    metadata={"llm_context": context_metadata} if context_metadata else None,
                )
            yield TaskStatusUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                status=TaskStatus(
                    state=TaskState.TASK_STATE_WORKING,
                    message=final_message,
                ),
            )

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
        """Нестreaming-вызов (vision/OCR и др.), совместим с ``LLMClient.invoke``."""
        del max_tokens, extra_body, extra_headers
        normalized_messages = _normalize_messages(messages)
        prepared_context = await prepare_messages_for_context_layer(
            normalized_messages,
            tools=None,
            llm_context=llm_context,
            llm_context_blocks=llm_context_blocks,
            llm_context_source_registry=llm_context_source_registry,
        )
        normalized_messages = prepared_context.messages
        context_metadata = llm_context_trace_metadata(prepared_context.compiled_context)
        response_format: JsonObject | None = None
        if json_output:
            response_format = {"type": "json_object"}
        await self._capture_call_to_redis(
            messages=normalized_messages,
            tools=None,
            response_format=response_format,
            llm_context=context_metadata,
        )
        mock_response = await self._get_response_async(normalized_messages)
        content_raw = mock_response.get("content", "")
        content = content_raw if isinstance(content_raw, str) else ""
        if json_output:
            stripped = content.strip()
            if not stripped:
                raise ValueError("MockLLM json_output requested but response content is empty")
            return parse_json_object(stripped, "mock_llm.invoke.response")
        return content

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
        reasoning_effort: str | None = None,
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
        reasoning_effort: str | None = None,
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
        reasoning_effort: str | None = None,
        extra_body: JsonObject | None = None,
        extra_headers: dict[str, str] | None = None,
        llm_context: LLMContextInput | None = None,
        llm_context_blocks: list[LLMContextBlock] | None = None,
        llm_context_source_registry: LLMContextSourceRegistry | None = None,
    ) -> Message | T:
        """
        Единый метод вызова MockLLM (совместим с LLMClient.chat).
        """
        del (
            temperature,
            top_p,
            top_k,
            max_tokens,
            frequency_penalty,
            presence_penalty,
            seed,
            reasoning_effort,
            extra_body,
            extra_headers,
        )
        normalized_messages = _normalize_messages(messages)

        response_format: JsonObject | None = None
        if response_model:
            json_schema = require_json_object(
                response_model.model_json_schema(),
                "mock_llm.response_model.schema",
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
        reasoning_parts: list[str] = []
        tool_calls: JsonArray = []
        last_status_text = ""

        async for event in self.stream(
            normalized_messages,
            tools=tools if not response_model else None,
            response_format=response_format,
            model=model,
            llm_context=llm_context,
            llm_context_blocks=llm_context_blocks,
            llm_context_source_registry=llm_context_source_registry,
        ):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.artifact and event.artifact.parts:
                    artifact_name = event.artifact.name
                    for part in event.artifact.parts:
                        if not part_has_text(part):
                            continue
                        if artifact_name == "reasoning":
                            reasoning_parts.append(part.text)
                        elif artifact_name != "reasoning":
                            content_parts.append(part.text)
            if isinstance(event, TaskStatusUpdateEvent) and event.status.HasField("message"):
                status_text = get_message_text(event.status.message)
                if status_text:
                    last_status_text = status_text
                if event.status.message.metadata:
                    metadata = mapping_from_struct(event.status.message.metadata)
                    metadata_tool_calls = metadata.get("tool_calls")
                    if metadata_tool_calls:
                        tool_calls = require_json_array(
                            metadata_tool_calls,
                            "mock_llm.status.message.metadata.tool_calls",
                        )

        content = "".join(content_parts)
        if response_model:
            reasoning_text = "".join(reasoning_parts)
            text_for_json = resolve_structured_output_source_text(
                content=content,
                last_status_text=last_status_text,
                reasoning_text=reasoning_text,
            )
            if not text_for_json.strip():
                raise ValueError(
                    "LLM structured output: пустой ответ (нет текста вне reasoning-артефакта и "
                    + "нет текста в финальном статусе задачи)"
                )
            structured_payload = parse_json_value(text_for_json, "mock_llm.structured_output")
            return response_model.model_validate(structured_payload)

        return build_a2a_message(
            role=Role.ROLE_AGENT,
            parts=[Part(text=content)],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )


_CAPTURE_ROLE_NAMES: dict[Role | int, str] = {
    Role.ROLE_USER: "user",
    Role.ROLE_AGENT: "agent",
}


def _normalize_message_for_capture(message: Message) -> JsonObject:
    """
    Превращает A2A `Message` в JSON-сериализуемое представление для журнала
    MockLLM. Текст склеивается из всех text Part-ов; raw Part представляется
    заглушкой `{file: True, mime_type: ...}` без bytes.
    """
    metadata = mapping_from_struct(message.metadata) if message.metadata else {}
    parts = list(message.parts)

    text_parts: list[str] = []
    serialized_parts: JsonArray = []
    for part in parts:
        if part_has_text(part):
            text_parts.append(part.text)
            serialized_parts.append({"type": "text", "text": part.text})
            continue
        if part_has_raw(part):
            mime_type = part.media_type if part.media_type else "application/octet-stream"
            serialized_parts.append({"type": "file", "mime_type": mime_type})

    safe_metadata: JsonObject = {}
    for key in ("system", "tool_call_id", "tool_calls"):
        if key in metadata:
            safe_metadata[key] = metadata[key]
    role_name = _CAPTURE_ROLE_NAMES.get(message.role)
    if role_name is None:
        raise ValueError(f"Unsupported A2A role for mock capture: {message.role!r}")
    return {
        "role": role_name,
        "text": "".join(text_parts),
        "parts": serialized_parts,
        "metadata": safe_metadata,
    }


def get_global_mock_llm(model: str = "mock-gpt-4") -> MockLLM | None:
    """Получает глобальный MockLLM для настройки в тестах"""
    return _global_mock_registry.get(model)


def get_or_create_global_mock_llm(model: str = "mock-gpt-4") -> MockLLM:
    """Получает или регистрирует process-local MockLLM."""
    mock_llm = _global_mock_registry.get(model)
    if mock_llm is None:
        mock_llm = MockLLM(model_name=model)
        _global_mock_registry[model] = mock_llm
    return mock_llm


def configure_mock_llm_redis(
    redis_client: RedisClient, model: str = "mock-gpt-4"
) -> MockLLM | None:
    """Настраивает MockLLM для чтения из Redis.

    Очередь ответов адресуется test scope текущего запроса
    (`mock_llm:responses:<scope>`), поэтому один процесс безопасно обслуживает
    параллельные тесты без общих ключей и скана.
    """
    mock_llm = get_global_mock_llm(model)
    if mock_llm:
        _ = mock_llm.set_redis_client(redis_client)
        logger.info("mock_llm.redis_configured")
    return mock_llm


async def pop_mock_array_response(
    redis_client: RedisClient, key: str
) -> MockLLMQueuedResponse | None:
    """
    Атомарно снимает один элемент JSON-массива по ключу (Lua POP).

    None — ключа нет или очередь исчерпана. Используется Mock Control System
    для tool/node/flow очередей.
    """
    payload = await redis_client.eval(_MOCK_LLM_REDIS_POP_SCRIPT, 1, key)
    if payload is None:
        return None
    if not isinstance(payload, str):
        raise ValueError("mock_control pop response must be a JSON string")
    parsed = parse_json_value(payload, "mock_control.pop_response")
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict):
        return require_json_object(parsed, "mock_control.pop_response")
    raise ValueError("mock_control pop response must be a string or JSON object")


async def setup_mock_responses_redis(
    redis_client: RedisClient,
    response_queue: list[MockLLMQueuedResponse],
    *,
    test_scope: str,
) -> None:
    """
    Записывает mock ответы в Redis-очередь конкретного test scope.

    Тест пишет очередь, а MockLLM в любом процессе (granian, TaskIQ worker,
    in-process ASGI) читает её по тому же scope из своего request-контекста.
    """
    key = mock_llm_responses_key(test_scope)
    _ = await redis_client.set(
        key,
        json.dumps(response_queue),
        ttl=_MOCK_LLM_REDIS_TTL_SECONDS,
    )
    logger.info("mock_llm.redis_responses_written", count=len(response_queue), key=key)


async def clear_mock_responses_redis(
    redis_client: RedisClient,
    *,
    test_scope: str,
) -> None:
    """Удаляет очередь mock-ответов test scope из Redis."""
    _ = await redis_client.delete(mock_llm_responses_key(test_scope))


async def start_mock_llm_capture(redis_client: RedisClient, scope: str) -> str:
    """
    Готовит журнал вызовов MockLLM для test scope: очищает список
    `mock_llm:capture:<scope>`. Сама запись включается автоматически —
    MockLLM пишет журнал для любого вызова с активным test scope.
    """
    if not scope:
        raise ValueError("start_mock_llm_capture: scope не должен быть пустым")
    list_key = mock_llm_capture_key(scope)
    _ = await redis_client.delete(list_key)
    return list_key


async def stop_mock_llm_capture(redis_client: RedisClient, scope: str) -> None:
    """Удаляет журнал вызовов MockLLM для test scope."""
    _ = await redis_client.delete(mock_llm_capture_key(scope))


async def read_mock_llm_capture(redis_client: RedisClient, scope: str) -> list[JsonObject]:
    """Возвращает все записанные за scope вызовы MockLLM в порядке прихода."""
    capture_payloads = await redis_client.lrange(mock_llm_capture_key(scope), 0, -1)
    captured_calls: list[JsonObject] = []
    for capture_item in capture_payloads or []:
        captured_calls.append(parse_json_object(capture_item, "mock_llm.capture[]"))
    return captured_calls
