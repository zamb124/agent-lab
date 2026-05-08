"""
Mock LLM для тестов.
"""

import asyncio
import json
import os
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
from a2a.utils.message import get_message_text, new_agent_text_message
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

_global_mock_registry: Dict[str, "MockLLM"] = {}

# Атомарно: один элемент JSON-массива за вызов (несколько async LLM на одном ключе).
_MOCK_LLM_REDIS_POP_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
  return nil
end
local decoded = cjson.decode(raw)
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
        self.model_name = model_name
        self.llm_provider = "mock"
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

        key = _mock_redis_key()
        try:
            raw = await self._redis_client.eval(_MOCK_LLM_REDIS_POP_SCRIPT, 1, key)
            if raw is None:
                return None
            response = json.loads(raw)
            logger.info("MockLLM: ответ из Redis (очередь уменьшена атомарно)")
            return response
        except Exception as e:
            logger.warning(f"MockLLM: ошибка чтения из Redis: {e}")

        return None

    async def _capture_call_to_redis(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]],
        response_format: Optional[Dict[str, Any]],
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
            logger.warning(f"MockLLM capture: ошибка чтения scope: {exc}")
            return
        if scope is None:
            return
        if isinstance(scope, bytes):
            scope = scope.decode("utf-8")
        if not scope:
            return

        normalized_messages = [_normalize_message_for_capture(m) for m in messages]
        record = {
            "model": self.model_name,
            "messages": normalized_messages,
            "tools": tools or [],
            "response_format": response_format,
        }
        try:
            await self._redis_client.rpush(
                _mock_capture_key(scope), json.dumps(record, ensure_ascii=False)
            )
        except Exception as exc:
            logger.warning(f"MockLLM capture: ошибка записи в Redis: {exc}")

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
        **_: Any,
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

        await self._capture_call_to_redis(
            messages=messages,
            tools=tools,
            response_format=response_format,
        )

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

        # Tool calls: как в LLMClient.stream — сначала статус с tool_calls+usage, затем
        # второй статус (часто только usage), иначе LlmNodeRunner затирал бы tool_calls.
        if tool_calls:
            usage_data = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text=content))],
                metadata={"tool_calls": tool_calls, "usage": usage_data},
            )
            yield TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(state=TaskState.working, message=message),
                final=False,
            )
            final_message = new_agent_text_message(content) if content else None
            if final_message:
                final_message.metadata = {"usage": usage_data}
            yield TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
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
                )
            yield TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(state=TaskState.completed, message=final_message),
                final=False,
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
        reasoning_effort: Optional[str] = None,
        extra_body: Optional[Dict[str, Any]] = None,
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
        reasoning_effort: Optional[str] = None,
        extra_body: Optional[Dict[str, Any]] = None,
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
        reasoning_effort: Optional[str] = None,
        extra_body: Optional[Dict[str, Any]] = None,
    ) -> Message | T:
        """
        Единый метод вызова MockLLM (совместим с LLMClient.chat).
        """
        del seed, reasoning_effort, extra_body
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
        last_status_text = ""

        async for event in self.stream(
            normalized,
            tools=tools if not response_model else None,
            response_format=response_format,
        ):
            if isinstance(event, TaskArtifactUpdateEvent):
                if (
                    event.artifact
                    and event.artifact.name != "reasoning"
                    and event.artifact.parts
                ):
                    for part in event.artifact.parts:
                        if hasattr(part, "root") and hasattr(part.root, "text"):
                            content_parts.append(part.root.text)
            if isinstance(event, TaskStatusUpdateEvent) and event.status:
                if event.status.message:
                    txt = get_message_text(event.status.message)
                    if txt:
                        last_status_text = txt
                if event.status.message and event.status.message.metadata:
                    tc = event.status.message.metadata.get("tool_calls")
                    if tc:
                        tool_calls = tc
        
        content = "".join(content_parts)
        if response_model:
            text_for_json = content if content.strip() else last_status_text
            if not text_for_json.strip():
                raise ValueError(
                    "LLM structured output: пустой ответ (нет текста вне reasoning-артефакта "
                    "и нет текста в финальном статусе задачи)"
                )
            data = json.loads(text_for_json)
            return response_model.model_validate(data)
        
        return Message(
            messageId=str(uuid.uuid4()),
            role=Role.agent,
            parts=[Part(root=TextPart(text=content))],
            metadata={"tool_calls": tool_calls} if tool_calls else None,
        )


def _normalize_message_for_capture(message: Any) -> Dict[str, Any]:
    """
    Превращает A2A `Message` (или dict) в JSON-сериализуемое представление
    для журнала MockLLM. Текст склеивается из всех TextPart-ов; FilePart
    представляется заглушкой `{file: True, mime_type: ...}` без bytes.
    """
    if isinstance(message, Message):
        role = message.role
        metadata = message.metadata or {}
        parts = message.parts or []
    elif isinstance(message, dict):
        role = message.get("role", "user")
        metadata = message.get("metadata") or {}
        parts = message.get("parts") or []
    else:
        return {"role": "user", "text": str(message), "parts": [], "metadata": {}}

    text_parts: List[str] = []
    raw_parts: List[Dict[str, Any]] = []
    for part in parts:
        root = getattr(part, "root", None)
        if root is None and isinstance(part, dict):
            root = part.get("root", part)
        if root is None:
            continue
        text = None
        if hasattr(root, "text"):
            text = getattr(root, "text", None)
        elif isinstance(root, dict) and "text" in root:
            text = root["text"]
        if isinstance(text, str):
            text_parts.append(text)
            raw_parts.append({"type": "text", "text": text})
            continue
        file_obj = None
        if hasattr(root, "file"):
            file_obj = getattr(root, "file")
        elif isinstance(root, dict) and "file" in root:
            file_obj = root["file"]
        if file_obj is not None:
            mime = None
            if hasattr(file_obj, "mime_type"):
                mime = getattr(file_obj, "mime_type")
            elif isinstance(file_obj, dict):
                mime = file_obj.get("mimeType") or file_obj.get("mime_type")
            raw_parts.append({"type": "file", "mime_type": mime or "application/octet-stream"})

    role_str = role.value if hasattr(role, "value") else str(role)
    safe_metadata: Dict[str, Any] = {}
    for key in ("system", "tool_call_id", "tool_calls"):
        if key in metadata:
            safe_metadata[key] = metadata[key]
    return {
        "role": role_str,
        "text": "".join(text_parts),
        "parts": raw_parts,
        "metadata": safe_metadata,
    }


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
    *,
    key_override: Optional[str] = None,
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
    await redis_client.set(key, json.dumps(response_queue))
    logger.info(f"MockLLM: записано {len(response_queue)} ответов в Redis (key={key})")


async def clear_mock_responses_redis(
    redis_client,
    *,
    key_override: Optional[str] = None,
) -> None:
    """Очищает mock ответы из Redis."""
    key = key_override or _mock_redis_key()
    await redis_client.delete(key)


async def start_mock_llm_capture(redis_client, scope: str) -> str:
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
    await redis_client.delete(list_key)
    await redis_client.set(_MOCK_CAPTURE_SCOPE_KEY, scope)
    return list_key


async def stop_mock_llm_capture(redis_client, scope: str) -> None:
    """Снимает активный capture-scope и удаляет его список."""
    await redis_client.delete(_MOCK_CAPTURE_SCOPE_KEY)
    await redis_client.delete(_mock_capture_key(scope))


async def read_mock_llm_capture(redis_client, scope: str) -> List[Dict[str, Any]]:
    """Возвращает все записанные за scope вызовы MockLLM в порядке прихода."""
    raw = await redis_client.lrange(_mock_capture_key(scope), 0, -1)
    out: List[Dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, bytes):
            item = item.decode("utf-8")
        out.append(json.loads(item))
    return out

