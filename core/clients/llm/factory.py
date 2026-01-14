"""
LLM клиент.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
ВСЕ ТИПЫ ИЗ a2a-sdk!
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING
import httpx
from core.http import get_httpx_client
from a2a.types import (
    Artifact,
    FilePart,
    FileWithBytes,
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

from core.config import get_settings
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState
from core.clients.llm.mock import (
    MockLLM,
    _global_mock_registry,
    get_global_mock_llm,
)

logger = get_logger(__name__)

# A2A событие от LLM
StreamEvent = TaskArtifactUpdateEvent | TaskStatusUpdateEvent


def _extract_content_parts(parts: List[Any]) -> tuple[List[Dict[str, Any]], bool]:
    """
    Извлекает content parts из списка A2A parts.
    
    Returns:
        Tuple (content_parts, has_files) где:
        - content_parts: список OpenAI content parts
        - has_files: True если есть файлы (нужен multimodal формат)
    """
    content_parts: List[Dict[str, Any]] = []
    has_files = False
    
    for part in parts:
        # Получаем root - может быть вложенный в Part или напрямую
        if hasattr(part, "root"):
            root = part.root
        elif isinstance(part, dict):
            root = part.get("root", part)
        else:
            continue
        
        # TextPart
        if isinstance(root, TextPart):
            content_parts.append({"type": "text", "text": root.text})
        elif isinstance(root, dict) and "text" in root:
            content_parts.append({"type": "text", "text": root["text"]})
        
        # FilePart - конвертируем в image_url
        elif isinstance(root, FilePart):
            has_files = True
            file_obj = root.file
            if isinstance(file_obj, FileWithBytes):
                mime_type = file_obj.mime_type or "image/png"
                b64_data = file_obj.bytes
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                })
        elif isinstance(root, dict) and "file" in root:
            has_files = True
            file_obj = root["file"]
            if isinstance(file_obj, dict) and "bytes" in file_obj:
                mime_type = file_obj.get("mimeType") or file_obj.get("mime_type") or "image/png"
                b64_data = file_obj["bytes"]
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                })
    
    return content_parts, has_files


def _message_to_openai(message: Message | Dict[str, Any] | str) -> Dict[str, Any]:
    """
    A2A Message в формат OpenAI API.
    
    Поддерживает:
    - Message объекты
    - dict (после десериализации из state)
    - строки
    - Multimodal: TextPart + FilePart
    """
    role_map = {
        Role.user: "user",
        Role.agent: "assistant",
        "user": "user",
        "agent": "assistant",
    }

    if isinstance(message, str):
        # Строковое представление Message объекта
        if "context_id=" in message and "parts=" in message and "role=" in message:
            text_match = re.search(r"text='([^']*)'", message)
            if text_match:
                content = text_match.group(1)
            else:
                text_match = re.search(r'text="([^"]*)"', message)
                content = text_match.group(1) if text_match else message
            
            role_str = "user"
            if "role=<Role.agent:" in message or "role='agent'" in message:
                role_str = "assistant"
            
            return {"role": role_str, "content": content}
        
        return {"role": "user", "content": message}

    # Извлекаем role и metadata
    if isinstance(message, dict):
        role_raw = message.get("role", "user")
        role = role_raw if isinstance(role_raw, (Role, str)) else "user"
        metadata = message.get("metadata") or {}
        parts = message.get("parts", [])
        
        # Если уже есть content напрямую (OpenAI формат)
        if "content" in message and message["content"]:
            return {
                "role": role_map.get(role, str(role)),
                "content": message["content"],
            }
    else:
        # Message объект
        role = message.role
        metadata = message.metadata or {}
        parts = message.parts

    # Извлекаем content parts (с поддержкой FilePart)
    content_parts, has_files = _extract_content_parts(parts)
    
    # Определяем итоговый content
    if has_files:
        # Multimodal формат - список parts
        content = content_parts
    else:
        # Текстовый формат - склеиваем в строку
        content = "".join(p["text"] for p in content_parts if p.get("type") == "text")

    # Определяем role для результата
    is_system = metadata.get("system", False)
    result_role = "system" if is_system else role_map.get(role, "user")
    
    if metadata.get("tool_call_id"):
        result_role = "tool"

    result: Dict[str, Any] = {
        "role": result_role,
        "content": content,
    }

    if metadata.get("tool_calls"):
        result["tool_calls"] = metadata["tool_calls"]
    
    if metadata.get("tool_call_id"):
        result["tool_call_id"] = metadata["tool_call_id"]

    return result


def _messages_to_openai(messages: List[Message | Dict[str, Any] | str]) -> List[Dict[str, Any]]:
    """Внутренняя функция - список A2A Message в формат OpenAI API.
    
    Поддерживает Message объекты, dict'ы и строки (включая строковые представления Message).
    """
    result = []
    for msg in messages:
        converted = _message_to_openai(msg)
        result.append(converted)
    
    return result


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
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.default_headers = default_headers or {}
        self.timeout = timeout

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream-first метод вызова LLM.

        Принимает A2A Message, возвращает A2A события.
        """
        task_id = task_id or str(uuid.uuid4())
        context_id = context_id or task_id

        openai_messages = _messages_to_openai(messages)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.default_headers,
        }

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if self.max_tokens:
            body["max_tokens"] = self.max_tokens

        if tools:
            body["tools"] = tools

        logger.debug(f"LLM request: messages={len(openai_messages)}, tools={len(tools) if tools else 0}")
        
        # Логируем полный body для отладки (без секретных данных)
        debug_body = {**body}
        if "messages" in debug_body:
            debug_body["messages"] = [
                {**msg, "content": msg["content"][:200] + "..." if len(msg.get("content", "")) > 200 else msg.get("content", "")}
                for msg in debug_body["messages"]
            ]
        logger.debug(f"LLM request body: {json.dumps(debug_body, indent=2, ensure_ascii=False)}")

        full_content = ""
        full_reasoning = ""
        tool_calls_buffer: Dict[int, Dict[str, Any]] = {}
        usage_data: Dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        async with get_httpx_client(timeout=self.timeout, proxy=True) as client:
            try:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", headers=headers, json=body
                ) as response:
                    if response.status_code != 200:
                        # Для stream response пытаемся прочитать тело ошибки
                        error_text = f"HTTP {response.status_code}"
                        try:
                            # Читаем первые байты ответа для получения деталей ошибки
                            error_chunks = []
                            async for chunk in response.aiter_bytes():
                                error_chunks.append(chunk)
                                if len(b''.join(error_chunks)) > 2000:  # Ограничиваем размер
                                    break
                            if error_chunks:
                                full_error = b''.join(error_chunks).decode('utf-8', errors='ignore')
                                # Пытаемся найти JSON в ответе
                                try:
                                    json_match = re.search(r'\{.*\}', full_error, re.DOTALL)
                                    if json_match:
                                        error_json = json.loads(json_match.group())
                                        error_text = json.dumps(error_json, indent=2, ensure_ascii=False)
                                    else:
                                        error_text = full_error[:1000]
                                except:
                                    error_text = full_error[:1000]
                        except Exception as e:
                            logger.debug(f"Could not read error body: {e}")
                        
                        logger.error(f"LLM API error {response.status_code}: {error_text}")
                        logger.error(f"Request URL: {self.base_url}/chat/completions")
                        logger.error(f"Request model: {self.model}")
                        logger.error(f"Request messages count: {len(openai_messages)}")
                        # Логируем первые и последние сообщения для отладки
                        if openai_messages:
                            logger.error(f"First message role: {openai_messages[0].get('role')}, content length: {len(openai_messages[0].get('content', ''))}")
                            if len(openai_messages) > 1:
                                logger.error(f"Last message role: {openai_messages[-1].get('role')}, content length: {len(openai_messages[-1].get('content', ''))}")
                        response.raise_for_status()

                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue

                        data = line[6:]
                        if data == "[DONE]":
                            break

                        chunk = json.loads(data)
                        
                        # Парсим usage из последнего chunk (stream_options: include_usage)
                        if chunk.get("usage"):
                            usage = chunk["usage"]
                            usage_data["input_tokens"] = usage.get("prompt_tokens", 0)
                            usage_data["output_tokens"] = usage.get("completion_tokens", 0)
                            usage_data["total_tokens"] = usage.get("total_tokens", 0)
                        
                        if not chunk.get("choices"):
                            continue

                        delta = chunk["choices"][0].get("delta", {})
                        
                        # Логируем delta для отладки reasoning (только если есть подозрительные поля)
                        if delta.get("reasoning") or delta.get("reasoning_content") or delta.get("type") == "reasoning":
                            logger.debug(f"LLM delta with reasoning fields: {delta}")

                        if delta.get("content"):
                            text = delta["content"]
                            full_content += text
                            yield TaskArtifactUpdateEvent(
                                contextId=context_id,
                                taskId=task_id,
                                artifact=Artifact(
                                    artifactId=str(uuid.uuid4()), parts=[Part(root=TextPart(text=text))]
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
                        choice = chunk["choices"][0]
                        if not reasoning_text and choice.get("delta", {}).get("reasoning"):
                            reasoning_text = choice["delta"]["reasoning"]
                        
                        if reasoning_text:
                            full_reasoning += reasoning_text
                            logger.info(f"LLM reasoning chunk: {len(reasoning_text)} chars")
                            yield TaskArtifactUpdateEvent(
                                contextId=context_id,
                                taskId=task_id,
                                artifact=Artifact(
                                    artifactId=str(uuid.uuid4()),
                                    name="reasoning",
                                    parts=[Part(root=TextPart(text=reasoning_text))]
                                ),
                                append=True,
                                last_chunk=False,
                            )

                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                idx = tc["index"]
                                if idx not in tool_calls_buffer:
                                    tool_calls_buffer[idx] = {
                                        "id": tc.get("id", ""),
                                        "name": "",
                                        "arguments": "",
                                    }
                                if tc.get("id"):
                                    tool_calls_buffer[idx]["id"] = tc["id"]
                                if tc.get("function"):
                                    if tc["function"].get("name"):
                                        tool_calls_buffer[idx]["name"] = tc["function"]["name"]
                                    if tc["function"].get("arguments"):
                                        tool_calls_buffer[idx]["arguments"] += tc["function"][
                                            "arguments"
                                        ]
            except httpx.HTTPStatusError as e:
                logger.error(f"LLM API HTTP error: {e}")
                logger.error(f"Request URL: {self.base_url}/chat/completions")
                logger.error(f"Request model: {self.model}")
                raise

        if tool_calls_buffer:
            parsed_tool_calls = []
            for idx in sorted(tool_calls_buffer.keys()):
                tc_data = tool_calls_buffer[idx]
                try:
                    args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                parsed_tool_calls.append(
                    {
                        "id": tc_data["id"],
                        "type": "function",
                        "function": {"name": tc_data["name"], "arguments": tc_data["arguments"]},
                        "name": tc_data["name"],
                        "arguments": args,
                    }
                )

            message = Message(
                message_id=str(uuid.uuid4()),
                role=Role.agent,
                parts=[Part(root=TextPart(text=full_content))],
                metadata={"tool_calls": parsed_tool_calls, "usage": usage_data},
            )
            yield TaskStatusUpdateEvent(
                contextId=context_id,
                taskId=task_id,
                status=TaskStatus(state=TaskState.working, message=message),
                final=False,
            )

        final_message = new_agent_text_message(full_content) if full_content else None
        if final_message:
            final_message.metadata = {"usage": usage_data}
        yield TaskStatusUpdateEvent(
            contextId=context_id,
            taskId=task_id,
            status=TaskStatus(
                state=TaskState.completed if not tool_calls_buffer else TaskState.working,
                message=final_message,
            ),
            final=True,
        )

        logger.log_llm_response(
            {
                "content": full_content,
                "reasoning": full_reasoning if full_reasoning else None,
                "tool_calls": list(tool_calls_buffer.values()) if tool_calls_buffer else None,
            }
        )

    async def invoke(
        self,
        messages: List[Message],
        json_output: bool = False,
        max_tokens: Optional[int] = None,
    ) -> str | Dict[str, Any]:
        """
        Non-streaming вызов LLM.
        
        Удобен для vision/OCR запросов где не нужен streaming.
        
        Args:
            messages: Список A2A сообщений (может содержать FilePart)
            json_output: Запросить JSON формат ответа
            max_tokens: Максимальное количество токенов
            
        Returns:
            Строка или dict (при json_output=True)
        """
        openai_messages = _messages_to_openai(messages)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.default_headers,
        }
        
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens or 4096,
        }
        
        if json_output:
            body["response_format"] = {"type": "json_object"}
        
        logger.info(f"LLM invoke: model={self.model}, messages={len(openai_messages)}, json_output={json_output}")
        
        async with get_httpx_client(timeout=self.timeout, proxy=True) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            
            if response.status_code != 200:
                error_text = response.text[:1000]
                logger.error(f"LLM invoke error: {response.status_code}, {error_text}")
                response.raise_for_status()
            
            result = response.json()
        
        content = result["choices"][0]["message"]["content"]
        
        logger.info(f"LLM invoke response: {len(content) if content else 0} chars")
        
        if json_output and content:
            return json.loads(content)
        
        return content or ""


def get_llm(
    model_name: Optional[str] = None, temperature: Optional[float] = None
) -> LLMClient | MockLLM:
    """Создает LLM клиент."""
    settings = get_settings()
    model = model_name or settings.llm.default_model

    is_testing = (
        os.environ.get("TESTING", "").lower() == "true"
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
        or os.environ.get("_PYTEST_RAISE") is not None
    )

    if is_testing and model and not model.startswith("mock-"):
        logger.warning(f"PYTEST detected: замена {model} на mock-gpt-4")
        model = "mock-gpt-4"

    if model.startswith("mock-"):
        if model not in _global_mock_registry:
            _global_mock_registry[model] = MockLLM(model_name=model)
        return _global_mock_registry[model]

    provider = settings.llm.provider
    model_config = settings.llm.models.get(model)
    temp = (
        temperature
        if temperature is not None
        else (model_config.temperature if model_config else settings.llm.temperature)
    )
    max_tokens = model_config.max_tokens if model_config else settings.llm.max_tokens
    timeout = settings.llm.timeout

    if provider == "openrouter":
        cfg = settings.llm.openrouter
        if not cfg or not cfg.api_key:
            raise ValueError("OpenRouter API key не настроен")

        return LLMClient(
            model=model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=temp,
            max_tokens=max_tokens,
            timeout=timeout,
            default_headers={
                "HTTP-Referer": cfg.site_url,
                "X-Title": cfg.site_name,
            },
        )

    if provider == "bothub":
        cfg = settings.llm.bothub
        if not cfg or not cfg.api_key:
            raise ValueError("Bothub API key не настроен")

        return LLMClient(
            model=model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=temp,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    if provider == "openai":
        cfg = settings.llm.openai
        if not cfg or not cfg.api_key:
            raise ValueError("OpenAI API key не настроен")

        return LLMClient(
            model=model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=temp,
            max_tokens=max_tokens,
            timeout=timeout,
        )

    raise ValueError(f"Неизвестный LLM провайдер: {provider}")


def get_llm_for_state(
    state: Optional["ExecutionState"] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
) -> LLMClient | MockLLM:
    """
    Создает LLM клиент с учётом mock конфига из state.
    
    Args:
        state: ExecutionState
        model_name: Имя модели
        temperature: Температура
        
    Returns:
        MockLLM или реальный LLMClient
    """
    from apps.agents.src.mock import get_mock_for_llm
    
    # Проверяем mock
    if state:
        mock_responses = get_mock_for_llm(state)
        if mock_responses:
            mock = MockLLM(model_name=model_name or "mock-gpt-4")
            mock.configure(response_queue=mock_responses)
            return mock
    
    # Реальный LLM клиент
    return get_llm(model_name, temperature)


def get_vision_llm(
    model_name: str = "google/gemini-2.5-flash-preview",
) -> LLMClient:
    """
    Создает LLM клиент для vision запросов.
    
    Args:
        model_name: Модель для vision (по умолчанию google/gemini-2.5-flash-preview)
        
    Returns:
        LLMClient настроенный для vision
    """
    settings = get_settings()
    provider = settings.llm.provider
    timeout = settings.llm.timeout
    
    if provider == "openrouter":
        cfg = settings.llm.openrouter
        if not cfg or not cfg.api_key:
            raise ValueError("OpenRouter API key не настроен")
        
        return LLMClient(
            model=model_name,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=0.1,
            timeout=timeout,
            default_headers={
                "HTTP-Referer": cfg.site_url,
                "X-Title": cfg.site_name,
            },
        )
    
    if provider == "bothub":
        cfg = settings.llm.bothub
        if not cfg or not cfg.api_key:
            raise ValueError("Bothub API key не настроен")
        
        return LLMClient(
            model=model_name,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=0.1,
            timeout=timeout,
        )
    
    if provider == "openai":
        cfg = settings.llm.openai
        if not cfg or not cfg.api_key:
            raise ValueError("OpenAI API key не настроен")
        
        return LLMClient(
            model=model_name,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=0.1,
            timeout=timeout,
        )
    
    raise ValueError(f"Неизвестный LLM провайдер: {provider}")


def setup_mock_responses(
    responses: Optional[Dict[str, str]] = None,
    tool_responses: Optional[Dict[str, Dict[str, Any]]] = None,
    default_response: Optional[str] = None,
    response_queue: Optional[List[Any]] = None,
    model_name: str = "mock-gpt-4",
) -> MockLLM:
    """Настройка mock ответов для тестов (локальная очередь)."""
    get_llm(model_name)
    mock_llm = get_global_mock_llm(model_name)

    if mock_llm:
        mock_llm.reset()
        mock_llm.configure(
            response_queue=response_queue,
            tool_responses=tool_responses,
            responses=responses,
            default_response=default_response,
        )

    return mock_llm
