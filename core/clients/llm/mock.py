"""
Mock LLM для тестов.
"""

import asyncio
import json
import os
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TypeAlias, TypeVar, overload

from a2a.types import (
    Artifact,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils.message import get_message_text, new_agent_text_message
from pydantic import BaseModel

from core.clients.llm.context_layer import (
    LLMContextInput,
    llm_context_trace_metadata,
    prepare_messages_for_context_layer,
)
from core.clients.llm.messages import (
    MessageInput,
    StreamEvent,
)
from core.clients.llm.messages import (
    normalize_messages as _normalize_messages,
)
from core.clients.redis_client import RedisClient
from core.llm_context import LLMContextBlock, LLMContextSourceRegistry
from core.logging import get_logger
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


def _mock_redis_key() -> str:
    """Ключ Redis для mock LLM ответов.

    При MOCK_LLM_REDIS_KEY (полное имя ключа, например mock_llm:responses:flows)
    процесс читает ту же очередь, что выставила фикстура mock_llm_redis для
    session-воркеров TaskIQ и uvicorn тестовых сервисов.

    Иначе уникальный ключ на pytest-xdist gw для in-process тестов без общего lane.
    """
    explicit = os.environ.get("MOCK_LLM_REDIS_KEY", "").strip()
    if explicit:
        return explicit
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    if worker:
        return f"mock_llm:responses:{worker}"
    return "mock_llm:responses"


def _mock_capture_key(scope: str) -> str:
    """
    Ключ Redis для журнала вызовов MockLLM (захват `messages`).

    `scope` — произвольная метка теста (UUID4); фикстура `mock_llm_capture`
    использует одну метку на тест и кладёт её в Redis (см.
    `_MOCK_CAPTURE_SCOPE_KEY`), а `MockLLM.stream` читает её и пишет
    каждый вызов в `mock_llm:capture:<scope>` как отдельный элемент списка.

    Без активной метки журнал не ведётся.
    """
    return f"mock_llm:capture:{scope}"


_MOCK_CAPTURE_SCOPE_KEY = "mock_llm:capture:active_scope"

_global_mock_registry: dict[str, "MockLLM"] = {}

# Атомарно: один элемент JSON-массива за вызов (несколько async LLM на одном ключе).
_MOCK_LLM_REDIS_POP_SCRIPT = """
local raw_payload = redis.call('GET', KEYS[1])
if not raw_payload then
  return nil
end
local decoded = cjson.decode(raw_payload)
if decoded == nil or #decoded == 0 then
  redis.call('DEL', KEYS[1])
  return nil
end
local head = table.remove(decoded, 1)
if #decoded == 0 then
  redis.call('DEL', KEYS[1])
else
  redis.call('SET', KEYS[1], cjson.encode(decoded))
end
return cjson.encode(head)
"""


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

    def set_redis_client(self, redis_client: RedisClient) -> "MockLLM":
        """Устанавливает Redis клиент для межпроцессного обмена."""
        self._redis_client = redis_client
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
        """Получает ответ из Redis (межпроцессная очередь)."""
        if not self._redis_client:
            return None

        key = _mock_redis_key()
        try:
            redis_response_payload = await self._redis_client.eval(
                _MOCK_LLM_REDIS_POP_SCRIPT, 1, key
            )
            if redis_response_payload is None:
                return None
            if not isinstance(redis_response_payload, str):
                raise ValueError("mock_llm redis response must be a JSON string")
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
    ) -> None:
        """
        Если фикстура теста выставила активный capture-scope в Redis,
        пишет в журнал `mock_llm:capture:<scope>` запись об одном вызове
        MockLLM (`messages`, `tools`, `response_format`, `model`).

        `messages` нормализуются как plain text + role + metadata (ключи
        tool_calls / tool_call_id / system / usage). FilePart-ы выписываются
        как `{"file": True, "mime_type": ...}` без bytes — журнал должен
        оставаться компактным даже для multimodal вызовов.
        """
        if not self._redis_client:
            return
        try:
            scope = await self._redis_client.get(_MOCK_CAPTURE_SCOPE_KEY)
        except Exception as exc:
            logger.warning(
                "mock_llm.capture_scope_read_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
        if scope is None:
            return
        if isinstance(scope, bytes):
            scope = scope.decode("utf-8")
        if not scope:
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
        try:
            _ = await self._redis_client.rpush(
                _mock_capture_key(scope), json.dumps(record, ensure_ascii=False)
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
            require_json_object(last_message.metadata, "message.metadata")
            if last_message.metadata
            else {}
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
        Stream метод - 100% реалистичная симуляция OpenAI streaming.

        Стримит по токенам (2-5 символов) как настоящая LLM.
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

        # Стримим reasoning по токенам (2-5 символов) как реальная LLM
        reasoning_artifact_id = str(uuid.uuid4())
        if reasoning:
            reasoning_offset = 0
            while reasoning_offset < len(reasoning):
                chunk_size = min(3, len(reasoning) - reasoning_offset)
                chunk = reasoning[reasoning_offset : reasoning_offset + chunk_size]
                reasoning_offset += chunk_size

                is_last_reasoning_chunk = reasoning_offset >= len(reasoning)
                is_last_reasoning_overall = is_last_reasoning_chunk and not content and not tool_calls

                yield TaskArtifactUpdateEvent(
                    context_id=context_id,
                    task_id=task_id,
                    artifact=Artifact(
                        artifact_id=reasoning_artifact_id,
                        name="reasoning",
                        parts=[Part(root=TextPart(text=chunk))]
                    ),
                    append=True,
                    last_chunk=is_last_reasoning_overall,
                )
                await asyncio.sleep(0.005)

        # Стримим контент по токенам (2-5 символов) как реальная LLM
        if content:
            content_offset = 0
            while content_offset < len(content):
                # Размер чанка 2-5 символов (имитация токенов)
                chunk_size = min(3, len(content) - content_offset)
                chunk = content[content_offset : content_offset + chunk_size]
                content_offset += chunk_size

                is_last_content = content_offset >= len(content)
                is_last = is_last_content and not tool_calls

                yield TaskArtifactUpdateEvent(
                    context_id=context_id,
                    task_id=task_id,
                    artifact=Artifact(
                        artifact_id=artifact_id, parts=[Part(root=TextPart(text=chunk))]
                    ),
                    append=True,
                    last_chunk=is_last,
                )
                await asyncio.sleep(0.005)

        # Tool calls: как в LLMClient.stream — сначала статус с tool_calls+usage, затем
        # второй статус (часто только usage), иначе LlmNodeRunner затирал бы tool_calls.
        if tool_calls:
            usage_data: JsonObject = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text=content))],
                metadata={
                    "tool_calls": tool_calls,
                    "usage": usage_data,
                    **({"llm_context": context_metadata} if context_metadata else {}),
                },
            )
            yield TaskStatusUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                status=TaskStatus(state=TaskState.working, message=message),
                final=False,
            )
            final_message = new_agent_text_message(content) if content else None
            if final_message:
                final_message.metadata = {
                    "usage": usage_data,
                    **({"llm_context": context_metadata} if context_metadata else {}),
                }
            yield TaskStatusUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                status=TaskStatus(
                    state=TaskState.working,
                    message=final_message,
                ),
                final=False,
            )
        else:
            # Без tool_calls: статус завершения шага LLM (не конец A2A-задачи, см. factory.stream).
            final_message = None
            if content:
                final_message = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.agent,
                    parts=[Part(root=TextPart(text=content))],
                    metadata={"llm_context": context_metadata} if context_metadata else None,
                )
            yield TaskStatusUpdateEvent(
                context_id=context_id,
                task_id=task_id,
                status=TaskStatus(state=TaskState.completed, message=final_message),
                final=False,
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
        response_format: JsonObject | None = None
        if json_output:
            response_format = {"type": "json_object"}
        await self._capture_call_to_redis(
            messages=normalized_messages,
            tools=None,
            response_format=response_format,
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
                if (
                    event.artifact
                    and event.artifact.name != "reasoning"
                    and event.artifact.parts
                ):
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
                        "mock_llm.status.message.metadata",
                    )
                    metadata_tool_calls = metadata.get("tool_calls")
                    if metadata_tool_calls:
                        tool_calls = require_json_array(
                            metadata_tool_calls,
                            "mock_llm.status.message.metadata.tool_calls",
                        )

        content = "".join(content_parts)
        if response_model:
            text_for_json = content if content.strip() else last_status_text
            if not text_for_json.strip():
                raise ValueError(
                    "LLM structured output: пустой ответ (нет текста вне reasoning-артефакта и "
                    + "нет текста в финальном статусе задачи)"
                )
            structured_payload = parse_json_value(text_for_json, "mock_llm.structured_output")
            return response_model.model_validate(structured_payload)

        return Message(
            message_id=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )


def _normalize_message_for_capture(message: Message) -> JsonObject:
    """
    Превращает A2A `Message` в JSON-сериализуемое представление для журнала
    MockLLM. Текст склеивается из всех TextPart-ов; FilePart представляется
    заглушкой `{file: True, mime_type: ...}` без bytes.
    """
    metadata = (
        require_json_object(message.metadata, "message.metadata")
        if message.metadata
        else {}
    )
    parts = message.parts or []

    text_parts: list[str] = []
    serialized_parts: JsonArray = []
    for part in parts:
        root = part.root
        if isinstance(root, TextPart):
            text_parts.append(root.text)
            serialized_parts.append({"type": "text", "text": root.text})
            continue
        if isinstance(root, FilePart):
            file_obj = root.file
            mime_type = file_obj.mime_type or "application/octet-stream"
            serialized_parts.append({"type": "file", "mime_type": mime_type})

    safe_metadata: JsonObject = {}
    for key in ("system", "tool_call_id", "tool_calls"):
        if key in metadata:
            safe_metadata[key] = metadata[key]
    return {
        "role": message.role.value,
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
    """Настраивает MockLLM для чтения из Redis."""
    mock_llm = get_global_mock_llm(model)
    if mock_llm:
        _ = mock_llm.set_redis_client(redis_client)
        logger.info("mock_llm.redis_configured")
    return mock_llm


async def setup_mock_responses_redis(
    redis_client: RedisClient,
    response_queue: list[MockLLMQueuedResponse],
    *,
    key_override: str | None = None,
) -> None:
    """
    Записывает mock ответы в Redis для межпроцессного обмена.

    Тест вызывает эту функцию, Worker читает ответы из Redis.
    Это позволяет тестам контролировать ответы даже когда Worker
    в отдельном subprocess.

    key_override: если задан, используется вместо автоматического ключа.
    Для real_taskiq фикстура mock_llm_redis задаёт ключ mock_llm:responses:<lane>;
    у соответствующего worker и uvicorn в TEST окружение задаёт MOCK_LLM_REDIS_KEY
    на тот же ключ (PYTEST_XDIST_WORKER снят у subprocess).
    """
    key = key_override or _mock_redis_key()
    _ = await redis_client.set(key, json.dumps(response_queue))
    logger.info("mock_llm.redis_responses_written", count=len(response_queue), key=key)


async def clear_mock_responses_redis(
    redis_client: RedisClient,
    *,
    key_override: str | None = None,
) -> None:
    """Очищает mock ответы из Redis."""
    key = key_override or _mock_redis_key()
    _ = await redis_client.delete(key)


async def start_mock_llm_capture(redis_client: RedisClient, scope: str) -> str:
    """
    Включает запись каждого вызова MockLLM (`messages`, `tools`,
    `response_format`, `model`) в Redis-список `mock_llm:capture:<scope>`.

    Действует процессно-глобально: пока стоит ключ `mock_llm:capture:active_scope`,
    `MockLLM.stream` пишет в `mock_llm:capture:<scope>`. Снимается через
    `stop_mock_llm_capture`. Возвращает имя ключа списка.
    """
    if not scope:
        raise ValueError("start_mock_llm_capture: scope не должен быть пустым")
    list_key = _mock_capture_key(scope)
    _ = await redis_client.delete(list_key)
    _ = await redis_client.set(_MOCK_CAPTURE_SCOPE_KEY, scope)
    return list_key


async def stop_mock_llm_capture(redis_client: RedisClient, scope: str) -> None:
    """Снимает активный capture-scope и удаляет его список."""
    _ = await redis_client.delete(_MOCK_CAPTURE_SCOPE_KEY)
    _ = await redis_client.delete(_mock_capture_key(scope))


async def read_mock_llm_capture(redis_client: RedisClient, scope: str) -> list[JsonObject]:
    """Возвращает все записанные за scope вызовы MockLLM в порядке прихода."""
    capture_payloads = await redis_client.lrange(_mock_capture_key(scope), 0, -1)
    captured_calls: list[JsonObject] = []
    for capture_item in capture_payloads or []:
        captured_calls.append(parse_json_object(capture_item, "mock_llm.capture[]"))
    return captured_calls
