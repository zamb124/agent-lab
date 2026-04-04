"""
Mock LLM для тестов.
"""

import asyncio
import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, TypeVar, Union, overload

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
from a2a.utils.message import get_message_text
from pydantic import BaseModel

from core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Типы для messages
MessageInput = Union[
    str,
    List[str],
    Message,
    List[Message],
    Dict[str, Any],
    List[Dict[str, Any]],
]

# A2A событие от LLM
StreamEvent = TaskArtifactUpdateEvent | TaskStatusUpdateEvent

MOCK_REDIS_KEY = "mock_llm:responses"

_global_mock_registry: Dict[str, "MockLLM"] = {}


class MockLLM:
    """
    Mock LLM для тестов.
    Работает с A2A типами.
    
    Поддерживает Redis для межпроцессного обмена mock ответами:
    - Тест записывает ответы в Redis
    - Worker читает ответы из Redis
    """

    def __init__(self, model_name: str = "mock-gpt-4"):
        self.model_name = model_name
        self._response_queue: List[Any] = []
        self._responses: Dict[str, str] = {}
        self._tool_responses: Dict[str, Dict[str, Any]] = {}
        self._default_response: str = "Mock LLM ответ"
        self._redis_client = None

    def set_redis_client(self, redis_client) -> "MockLLM":
        """Устанавливает Redis клиент для межпроцессного обмена."""
        self._redis_client = redis_client
        return self

    def configure(
        self,
        response_queue: Optional[List[Any]] = None,
        tool_responses: Optional[Dict[str, Dict[str, Any]]] = None,
        responses: Optional[Dict[str, str]] = None,
        default_response: Optional[str] = None,
    ) -> "MockLLM":
        """Настройка mock ответов."""
        if response_queue is not None:
            self._response_queue = list(response_queue)
            logger.info(f"MockLLM: настроена очередь из {len(self._response_queue)} ответов")

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

    async def _get_redis_response(self) -> Optional[Any]:
        """Получает ответ из Redis (межпроцессная очередь)."""
        if not self._redis_client:
            return None
        
        try:
            data = await self._redis_client.get(MOCK_REDIS_KEY)
            if data:
                responses = json.loads(data)
                if responses:
                    response = responses.pop(0)
                    if responses:
                        await self._redis_client.set(MOCK_REDIS_KEY, json.dumps(responses))
                    else:
                        await self._redis_client.delete(MOCK_REDIS_KEY)
                    logger.info(f"MockLLM: ответ из Redis (осталось {len(responses)})")
                    return response
        except Exception as e:
            logger.warning(f"MockLLM: ошибка чтения из Redis: {e}")
        
        return None

    def _get_response(self, messages: List[Message]) -> Dict[str, Any]:
        """Внутренний метод получения ответа."""
        # Сначала локальная очередь
        if self._response_queue:
            response = self._response_queue.pop(0)
            logger.debug(f"MockLLM: ответ из очереди (осталось {len(self._response_queue)})")
            return self._process_response(response, messages)

        return self._generate_from_patterns(messages)
    
    async def _get_response_async(self, messages: List[Message]) -> Dict[str, Any]:
        """Асинхронный метод получения ответа с Redis поддержкой."""
        # Локальная очередь приоритетнее Redis: в одном тесте uvicorn ест очередь
        # из configure_mock_llm, а worker — из ключа mock_llm:responses без пересечения.
        if self._response_queue:
            response = self._response_queue.pop(0)
            logger.debug(f"MockLLM: ответ из очереди (осталось {len(self._response_queue)})")
            return self._process_response(response, messages)

        redis_response = await self._get_redis_response()
        if redis_response is not None:
            return self._process_response(redis_response, messages)

        return self._generate_from_patterns(messages)

    def _process_response(self, response: Any, messages: List[Message]) -> Dict[str, Any]:
        """Обрабатывает ответ из очереди"""
        if isinstance(response, dict):
            if response.get("type") == "tool_call":
                args = response.get("args", {})
                tool_call_id = response.get("id") or f"call_mock_{response['tool']}_{len(messages)}"
                return {
                    "content": "",
                    "reasoning": None,
                    "tool_calls": [
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {"name": response["tool"], "arguments": json.dumps(args)},
                            "name": response["tool"],
                            "arguments": args,
                        }
                    ],
                }
            elif response.get("type") == "tool_calls":
                # Множественные tool_calls - ПАРАЛЛЕЛЬНОЕ выполнение
                calls = response.get("calls", [])
                tool_calls = []
                for i, call in enumerate(calls):
                    args = call.get("args", {})
                    tool_name = call.get("tool")
                    tool_call_id = call.get("id") or f"call_mock_{tool_name}_{len(messages)}_{i}"
                    tool_calls.append({
                        "id": tool_call_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": json.dumps(args)},
                        "name": tool_name,
                        "arguments": args,
                    })
                return {
                    "content": "",
                    "reasoning": None,
                    "tool_calls": tool_calls,
                }
            elif response.get("type") == "text":
                return {
                    "content": response.get("content", self._default_response),
                    "reasoning": response.get("reasoning"),
                    "tool_calls": None,
                }
            elif response.get("type") == "structured_output":
                # Structured output возвращает JSON как content
                data = response.get("data", {})
                content = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else str(data)
                return {
                    "content": content,
                    "reasoning": response.get("reasoning"),
                    "tool_calls": None,
                }
            else:
                return {"content": str(response), "reasoning": None, "tool_calls": None}
        elif isinstance(response, str):
            return {"content": response, "reasoning": None, "tool_calls": None}
        else:
            return {"content": str(response), "reasoning": None, "tool_calls": None}

    def _generate_from_patterns(self, messages: List[Message]) -> Dict[str, Any]:
        """Генерирует ответ на основе паттернов"""
        if not messages:
            return {"content": self._default_response, "reasoning": None, "tool_calls": None}

        last_message = messages[-1]
        if hasattr(last_message, "parts"):
            content_str = get_message_text(last_message)
        else:
            content_str = ""
            for part in last_message.get("parts", []):
                if isinstance(part, dict):
                    root = part.get("root", part)
                    if isinstance(root, dict) and "text" in root:
                        content_str += root["text"]
        
        metadata = last_message.metadata if hasattr(last_message, "metadata") else last_message.get("metadata") or {}
        if metadata and metadata.get("tool_call_id"):
            for key, response in self._responses.items():
                if key.lower() in content_str.lower():
                    return {"content": response, "reasoning": None, "tool_calls": None}
            return {"content": content_str or self._default_response, "reasoning": None, "tool_calls": None}

        for key, tool_config in self._tool_responses.items():
            if key.lower() in content_str.lower():
                args = tool_config.get("args", {})
                return {
                    "content": "",
                    "reasoning": None,
                    "tool_calls": [
                        {
                            "id": f"call_mock_{tool_config['tool']}_{len(messages)}",
                            "type": "function",
                            "function": {
                                "name": tool_config["tool"],
                                "arguments": json.dumps(args),
                            },
                            "name": tool_config["tool"],
                            "arguments": args,
                        }
                    ],
                }

        for key, response in self._responses.items():
            if key.lower() in content_str.lower():
                return {"content": response, "reasoning": None, "tool_calls": None}

        return {"content": self._default_response, "reasoning": None, "tool_calls": None}

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream метод - 100% реалистичная симуляция OpenAI streaming.
        
        Стримит по токенам (2-5 символов) как настоящая LLM.
        Tool calls тоже стримятся по частям: сначала id, потом name, потом arguments кусками.
        
        Поддерживает Redis для межпроцессного обмена mock ответами.
        Поддерживает response_format для structured output.
        """

        task_id = task_id or str(uuid.uuid4())
        context_id = context_id or task_id
        artifact_id = str(uuid.uuid4())

        # Используем async метод для поддержки Redis
        response = await self._get_response_async(messages)
        content = response.get("content", "")
        reasoning = response.get("reasoning", "")
        tool_calls = response.get("tool_calls")

        # Стримим reasoning по токенам (2-5 символов) как реальная LLM
        reasoning_artifact_id = str(uuid.uuid4())
        if reasoning:
            pos = 0
            while pos < len(reasoning):
                chunk_size = min(3, len(reasoning) - pos)
                chunk = reasoning[pos : pos + chunk_size]
                pos += chunk_size
                
                is_last_reasoning_chunk = pos >= len(reasoning)
                is_last_reasoning_overall = is_last_reasoning_chunk and not content and not tool_calls
                
                yield TaskArtifactUpdateEvent(
                    contextId=context_id,
                    taskId=task_id,
                    artifact=Artifact(
                        artifactId=reasoning_artifact_id,
                        name="reasoning",
                        parts=[Part(root=TextPart(text=chunk))]
                    ),
                    append=True,
                    last_chunk=is_last_reasoning_overall,
                )
                await asyncio.sleep(0.005)

        # Стримим контент по токенам (2-5 символов) как реальная LLM
        if content:
            pos = 0
            while pos < len(content):
                # Размер чанка 2-5 символов (имитация токенов)
                chunk_size = min(3, len(content) - pos)
                chunk = content[pos : pos + chunk_size]
                pos += chunk_size
                
                is_last_content = pos >= len(content)
                is_last = is_last_content and not tool_calls
                
                yield TaskArtifactUpdateEvent(
                    contextId=context_id,
                    taskId=task_id,
                    artifact=Artifact(
                        artifactId=artifact_id, parts=[Part(root=TextPart(text=chunk))]
                    ),
                    append=True,
                    last_chunk=is_last,
                )
                await asyncio.sleep(0.005)

        # Tool calls стримятся по частям как в OpenAI
        if tool_calls:
            message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text=content))],
                metadata={"tool_calls": tool_calls},
            )
            yield TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(state=TaskState.working, message=message),
                final=False,
            )
        else:
            # Финальное событие - только если нет tool_calls
            # Если есть tool_calls, агент продолжит после их выполнения
            final_message = None
            if content:
                final_message = Message(
                    message_id=str(uuid.uuid4()),
                    role=Role.agent,
                    parts=[Part(root=TextPart(text=content))],
                )
            yield TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(state=TaskState.completed, message=final_message),
                final=True,
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
    ) -> Message | T:
        """
        Единый метод вызова MockLLM (совместим с LLMClient.chat).
        """
        normalized = _normalize_messages(messages)
        
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
        
        async for event in self.stream(
            normalized,
            tools=tools if not response_model else None,
            response_format=response_format,
        ):
            if isinstance(event, TaskArtifactUpdateEvent):
                if event.artifact and event.artifact.parts:
                    for part in event.artifact.parts:
                        if hasattr(part, "root") and hasattr(part.root, "text"):
                            content_parts.append(part.root.text)
            if hasattr(event, "status") and event.status:
                if event.status.message and event.status.message.metadata:
                    tc = event.status.message.metadata.get("tool_calls")
                    if tc:
                        tool_calls = tc
        
        content = "".join(content_parts)
        
        if response_model:
            data = json.loads(content)
            return response_model.model_validate(data)
        
        return Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )


def _normalize_messages(messages: MessageInput) -> List[Message]:
    """
    Нормализует различные форматы messages в List[Message].
    """
    if isinstance(messages, str):
        return [
            Message(
                messageId=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=messages))],
            )
        ]
    
    if isinstance(messages, Message):
        return [messages]
    
    if isinstance(messages, dict):
        role = Role.user if messages.get("role", "user") == "user" else Role.agent
        content = messages.get("content", "")
        return [
            Message(
                messageId=str(uuid.uuid4()),
                role=role,
                parts=[Part(root=TextPart(text=content))],
            )
        ]
    
    if isinstance(messages, list):
        if not messages:
            return []
        
        first = messages[0]
        
        if isinstance(first, str):
            result = []
            for i, text in enumerate(messages):
                role = Role.user if i % 2 == 0 else Role.agent
                result.append(
                    Message(
                        messageId=str(uuid.uuid4()),
                        role=role,
                        parts=[Part(root=TextPart(text=text))],
                    )
                )
            return result
        
        if isinstance(first, Message):
            return messages
        
        if isinstance(first, dict):
            result = []
            for msg in messages:
                role = Role.user if msg.get("role", "user") == "user" else Role.agent
                content = msg.get("content", "")
                result.append(
                    Message(
                        messageId=str(uuid.uuid4()),
                        role=role,
                        parts=[Part(root=TextPart(text=content))],
                    )
                )
            return result
    
    raise ValueError(f"Unsupported messages type: {type(messages)}")


def get_global_mock_llm(model_name: str = "mock-gpt-4") -> Optional[MockLLM]:
    """Получает глобальный MockLLM для настройки в тестах"""
    return _global_mock_registry.get(model_name)


def configure_mock_llm_redis(redis_client, model_name: str = "mock-gpt-4") -> Optional[MockLLM]:
    """Настраивает MockLLM для чтения из Redis."""
    mock_llm = get_global_mock_llm(model_name)
    if mock_llm:
        mock_llm.set_redis_client(redis_client)
        logger.info("MockLLM: настроен для чтения из Redis")
    return mock_llm


async def setup_mock_responses_redis(
    redis_client,
    response_queue: List[Any],
) -> None:
    """
    Записывает mock ответы в Redis для межпроцессного обмена.
    
    Тест вызывает эту функцию, Worker читает ответы из Redis.
    Это позволяет тестам контролировать ответы даже когда Worker
    в отдельном subprocess.
    """
    await redis_client.set(MOCK_REDIS_KEY, json.dumps(response_queue))
    logger.info(f"MockLLM: записано {len(response_queue)} ответов в Redis")


async def clear_mock_responses_redis(redis_client) -> None:
    """Очищает mock ответы из Redis."""
    await redis_client.delete(MOCK_REDIS_KEY)

