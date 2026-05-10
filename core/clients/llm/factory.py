"""
LLM клиент.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
ВСЕ ТИПЫ ИЗ a2a-sdk!
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, TypeVar, Union, TYPE_CHECKING, overload
import httpx
from pydantic import BaseModel

from core.http.client import ProxyStrategy, get_httpx_client
from core.variables import VarResolver, VariableResolutionError
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
from core.config.base import BaseSettings
from core.config.openai_v1_base_url import normalize_openai_v1_base_url
from core.config.llm_openai_compat import yandex_llm_openai_root_from_provider_cfg
from core.config.testing import is_testing as _is_testing
from core.clients.llm.logging import log_llm_stream_response
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState
from core.clients.llm.mock import (
    MockLLM,
    _global_mock_registry,
    get_global_mock_llm,
)
from core.clients.llm.model_routing import split_provider_prefixed_model

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


def _masked_headers(headers: Dict[str, str]) -> Dict[str, str]:
    sanitized = dict(headers)
    for key in list(sanitized.keys()):
        lk = key.lower()
        if lk == "authorization" or lk in ("api-key", "x-api-key") or lk.endswith("-api-key"):
            sanitized[key] = "***"
    return sanitized


def _yandex_openai_root(settings: BaseSettings) -> str:
    cfg = settings.llm.yandex
    if cfg is None:
        return normalize_openai_v1_base_url("https://llm.api.cloud.yandex.net/v1")
    return yandex_llm_openai_root_from_provider_cfg(cfg)


def _yandex_auth_headers(*, api_key: str, folder_id: str) -> Dict[str, str]:
    fid = folder_id.strip()
    if not fid:
        raise ValueError("Yandex LLM: folder_id пуст")
    key = api_key.strip()
    if not key:
        raise ValueError("Yandex LLM: api_key пуст")
    return {
        "Authorization": f"Api-Key {key}",
        "x-folder-id": fid,
    }


_YANDEX_MODEL_URI_PREFIXES = ("gpt://", "emb://")


def normalize_yandex_resource_model_uri(model: str, folder_id: str) -> str:
    """Заменяет сегмент каталога в gpt:// и emb:// на folder_id (согласование с x-folder-id)."""
    fid = folder_id.strip()
    if not fid:
        return model
    for prefix in _YANDEX_MODEL_URI_PREFIXES:
        if not model.startswith(prefix):
            continue
        rest = model[len(prefix) :]
        if "/" not in rest:
            return model
        old_folder, tail = rest.split("/", 1)
        if old_folder == fid:
            return model
        return f"{prefix}{fid}/{tail}"
    return model


def _pretty_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _merge_openai_compatible_usage_into_usage_data(
    usage: Dict[str, Any], usage_data: Dict[str, Any]
) -> None:
    """
    Заполняет usage_data из объекта usage финального чанка/ответа chat completions.

    Токены — стандартные поля OpenAI. Поля cost / cost_details — расширения
    (OpenRouter и др. совместимые шлюзы); пишем только если ключ есть и значение число.
    """
    usage_data["input_tokens"] = int(usage.get("prompt_tokens") or 0)
    usage_data["output_tokens"] = int(usage.get("completion_tokens") or 0)
    total = usage.get("total_tokens")
    if total is not None:
        usage_data["total_tokens"] = int(total)
    else:
        usage_data["total_tokens"] = usage_data["input_tokens"] + usage_data["output_tokens"]

    cost = usage.get("cost")
    if isinstance(cost, (int, float)):
        usage_data["provider_reported_cost"] = float(cost)

    details = usage.get("cost_details")
    if isinstance(details, dict):
        upstream = details.get("upstream_inference_cost")
        if isinstance(upstream, (int, float)):
            usage_data["provider_upstream_inference_cost"] = float(upstream)

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


def _normalize_messages(messages: MessageInput) -> List[Message]:
    """
    Нормализует различные форматы messages в List[Message].
    
    Поддерживает:
    - str: одно сообщение пользователя
    - List[str]: список сообщений (чередуются user/assistant)
    - Message: одно A2A сообщение
    - List[Message]: список A2A сообщений
    - Dict: одно сообщение в формате {"role": "user", "content": "text"}
    - List[Dict]: список сообщений в формате OpenAI
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
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.llm_provider = llm_provider if llm_provider is not None else _detect_provider(self.base_url)

    async def stream(
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
        reasoning_effort: Optional[str] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
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
            temperature: Температура генерации (переопределяет self.temperature)
            top_p: Top-P семплирование (nucleus sampling)
            top_k: Top-K семплирование
            max_tokens: Максимальное количество токенов (переопределяет self.max_tokens)
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

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.default_headers)
        if extra_headers:
            headers.update(extra_headers)

        actual_temperature = temperature if temperature is not None else self.temperature
        actual_max_tokens = max_tokens if max_tokens is not None else self.max_tokens

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": actual_temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        if actual_max_tokens:
            body["max_tokens"] = actual_max_tokens
        
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
            for key, val in extra_body.items():
                body[key] = val

        logger.debug(f"LLM request: messages={len(openai_messages)}, tools={len(tools) if tools else 0}, response_format={bool(response_format)}")
        logger.info(
            "LLM STREAM REQUEST:\n"
            f"{_pretty_json({'url': f'{self.base_url}/chat/completions', 'headers': _masked_headers(headers), 'body': body})}"
        )

        full_content = ""
        full_reasoning = ""
        tool_calls_buffer: Dict[int, Dict[str, Any]] = {}
        usage_data: Dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        stream_start_time = time.monotonic()

        async with get_httpx_client(timeout=self.timeout, strategy=ProxyStrategy.SMART) as client:
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
                            _merge_openai_compatible_usage_into_usage_data(chunk["usage"], usage_data)
                        
                        if not chunk.get("choices"):
                            continue

                        choice = chunk["choices"][0]
                        delta = choice.get("delta", {}) or {}

                        # Некоторые шлюзы отдают весь текст только в message.content финального чанка (delta пустой).
                        msg = choice.get("message")
                        if isinstance(msg, dict):
                            mc = msg.get("content")
                            if (
                                isinstance(mc, str)
                                and mc
                                and not delta.get("content")
                                and not full_content
                            ):
                                full_content = mc
                                yield TaskArtifactUpdateEvent(
                                    contextId=context_id,
                                    taskId=task_id,
                                    artifact=Artifact(
                                        artifactId=str(uuid.uuid4()),
                                        parts=[Part(root=TextPart(text=mc))],
                                    ),
                                    append=True,
                                    last_chunk=False,
                                )
                        
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
                        if not reasoning_text and choice.get("delta", {}).get("reasoning"):
                            reasoning_text = choice["delta"]["reasoning"]
                        
                        if reasoning_text:
                            full_reasoning += reasoning_text
                            logger.debug(f"LLM reasoning chunk: {len(reasoning_text)} chars")
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
        # final=False: это конец одного вызова LLM внутри задачи, не конец A2A-задачи.
        # completed+final=True рвёт EventSubscriber до node_complete и emit_complete канала.
        yield TaskStatusUpdateEvent(
            contextId=context_id,
            taskId=task_id,
            status=TaskStatus(
                state=TaskState.completed if not tool_calls_buffer else TaskState.working,
                message=final_message,
            ),
            final=False,
        )

        log_llm_stream_response(
            url=f"{self.base_url}/chat/completions",
            content=full_content,
            reasoning=full_reasoning if full_reasoning else None,
            tool_calls=list(tool_calls_buffer.values()) if tool_calls_buffer else None,
            usage=usage_data,
            provider=self.llm_provider,
            model=self.model,
            duration_ms=(time.monotonic() - stream_start_time) * 1000,
        )

    async def invoke(
        self,
        messages: List[Message],
        json_output: bool = False,
        max_tokens: Optional[int] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> str | Dict[str, Any]:
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

        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.default_headers)
        if extra_headers:
            headers.update(extra_headers)

        body: Dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens or 4096,
        }

        if json_output:
            body["response_format"] = {"type": "json_object"}

        if extra_body:
            for key, val in extra_body.items():
                body[key] = val

        logger.info(f"LLM invoke: model={self.model}, messages={len(openai_messages)}, json_output={json_output}")
        logger.info(
            "LLM INVOKE REQUEST:\n"
            f"{_pretty_json({'url': f'{self.base_url}/chat/completions', 'headers': _masked_headers(headers), 'body': body})}"
        )
        
        async with get_httpx_client(timeout=self.timeout, strategy=ProxyStrategy.SMART) as client:
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
            logger.info(f"LLM INVOKE RESPONSE:\n{_pretty_json(result)}")
        
        content = result["choices"][0]["message"]["content"]
        
        logger.info(f"LLM invoke response: {len(content) if content else 0} chars")
        
        if json_output and content:
            return json.loads(content)
        
        return content or ""

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
        reasoning_effort: Optional[str] = None,
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
        reasoning_effort: Optional[str] = None,
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
            
            # Function calling
            msg = await llm.chat(messages, tools=[...])
            if msg.metadata and msg.metadata.get("tool_calls"):
                ...
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
        last_status_text = ""

        async for event in self.stream(
            normalized,
            tools=tools if not response_model else None,
            response_format=response_format,
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


def _resolve_var(value: Optional[str], state: Optional["ExecutionState"]) -> Optional[str]:
    """Резолвит @var:path из state.variables по strict-контракту."""
    if not value:
        return None
    if not value.startswith("@var:"):
        return value
    if state is None:
        raise VariableResolutionError(
            f"Cannot resolve '{value}' without ExecutionState"
        )
    resolved = VarResolver.resolve_ref(value, state.variables or {})
    if not isinstance(resolved, str):
        raise VariableResolutionError(
            f"Variable '{value}' for LLM config must resolve to string"
        )
    if not resolved:
        raise VariableResolutionError(
            f"Variable '{value}' resolved to empty string"
        )
    return resolved


def _detect_provider(base_url: Optional[str]) -> Optional[str]:
    """Определяет провайдера по base_url."""
    if not base_url:
        return None
    if "provider_litserve" in base_url or "localhost:8014" in base_url or "127.0.0.1:8014" in base_url:
        return "provider_litserve"
    if "openrouter.ai" in base_url:
        return "openrouter"
    if "bothub.chat" in base_url:
        return "bothub"
    if "api.openai.com" in base_url:
        return "openai"
    if "llm.api.cloud.yandex.net" in base_url:
        return "yandex"
    return None


def get_llm(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    folder_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    state: Optional["ExecutionState"] = None,
) -> LLMClient | MockLLM:
    """
    Создает LLM клиент.
    
    Args:
        model_name: Имя модели
        temperature: Температура
        provider: Провайдер (openai, openrouter, bothub, provider_litserve, yandex)
        api_key: API ключ (напрямую или @var:my_key)
        base_url: Base URL провайдера (напрямую или @var:my_url)
        folder_id: Каталог Yandex Cloud (yandex); иначе из llm.yandex.folder_id
        max_tokens: Лимит токенов ответа (если None — из настроек модели / глобальных)
        state: ExecutionState для резолюции @var:
    """
    settings = get_settings()
    model = model_name or settings.llm.default_model
    split_prov, split_model = split_provider_prefixed_model(provider, model)
    if split_prov is not None:
        provider = split_prov
    model = split_model if split_model is not None else model

    _testing = _is_testing()

    if _testing and model and not model.startswith("mock-"):
        logger.warning(f"PYTEST detected: замена {model} на mock-gpt-4")
        model = "mock-gpt-4"

    if model.startswith("mock-"):
        if model not in _global_mock_registry:
            _global_mock_registry[model] = MockLLM(model_name=model)
        return _global_mock_registry[model]

    # Резолвим @var: если указаны
    resolved_api_key = _resolve_var(api_key, state)
    resolved_base_url = _resolve_var(base_url, state)
    resolved_folder_id = _resolve_var(folder_id, state)
    
    model_config = settings.llm.models.get(model)
    temp = (
        temperature
        if temperature is not None
        else (model_config.temperature if model_config else settings.llm.temperature)
    )
    resolved_max_tokens = (
        max_tokens
        if max_tokens is not None
        else (model_config.max_tokens if model_config else settings.llm.max_tokens)
    )
    timeout = settings.llm.timeout
    
    # Если указан кастомный api_key - используем его
    if resolved_api_key:
        actual_provider = provider or _detect_provider(resolved_base_url) or settings.llm.provider
        actual_base_url = resolved_base_url or _get_default_base_url(actual_provider, settings)

        default_headers: Dict[str, str] = {}
        # custom_openai_compatible: никаких vendor-default headers (только Authorization Bearer
        # в LLMClient.stream и опциональные extra_headers вызывающего кода).
        if actual_provider == "custom_openai_compatible":
            if not resolved_base_url:
                raise ValueError(
                    "custom_openai_compatible: base_url обязателен (URL OpenAI-совместимого endpoint компании)"
                )
        elif actual_provider == "openrouter" and settings.llm.openrouter:
            default_headers = {
                "HTTP-Referer": settings.llm.openrouter.site_url,
                "X-Title": settings.llm.openrouter.site_name,
            }
        if actual_provider == "yandex":
            yc = settings.llm.yandex
            platform_fid = (
                str(yc.folder_id).strip()
                if yc and yc.folder_id and str(yc.folder_id).strip()
                else ""
            )
            override_fid = (
                str(resolved_folder_id).strip()
                if resolved_folder_id and str(resolved_folder_id).strip()
                else ""
            )
            effective_folder = override_fid or platform_fid
            if not effective_folder:
                raise ValueError(
                    "Yandex LLM: задайте folder_id в переопределении ноды/ресурса "
                    "или llm.yandex.folder_id"
                )
            default_headers = _yandex_auth_headers(
                api_key=resolved_api_key,
                folder_id=effective_folder,
            )
            model = normalize_yandex_resource_model_uri(model, effective_folder)

        if actual_provider == "yandex":
            actual_base_url = normalize_openai_v1_base_url(str(actual_base_url).strip())

        logger.info(f"[get_llm] Using custom api_key for provider={actual_provider}, base_url={actual_base_url}")
        return LLMClient(
            model=model,
            api_key=resolved_api_key,
            base_url=actual_base_url,
            temperature=temp,
            max_tokens=resolved_max_tokens,
            timeout=timeout,
            default_headers=default_headers,
            llm_provider=actual_provider,
        )
    
    # Иначе используем системный конфиг
    actual_provider = provider or settings.llm.provider

    if actual_provider == "openrouter":
        cfg = settings.llm.openrouter
        if not cfg or not cfg.api_key:
            raise ValueError("OpenRouter API key не настроен")

        return LLMClient(
            model=model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=temp,
            max_tokens=resolved_max_tokens,
            timeout=timeout,
            default_headers={
                "HTTP-Referer": cfg.site_url,
                "X-Title": cfg.site_name,
            },
            llm_provider=actual_provider,
        )

    if actual_provider == "bothub":
        cfg = settings.llm.bothub
        if not cfg or not cfg.api_key:
            raise ValueError("Bothub API key не настроен")

        return LLMClient(
            model=model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=temp,
            max_tokens=resolved_max_tokens,
            timeout=timeout,
            llm_provider=actual_provider,
        )

    if actual_provider == "openai":
        cfg = settings.llm.openai
        if not cfg or not cfg.api_key:
            raise ValueError("OpenAI API key не настроен")

        return LLMClient(
            model=model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=temp,
            max_tokens=resolved_max_tokens,
            timeout=timeout,
            llm_provider=actual_provider,
        )

    if actual_provider == "yandex":
        cfg = settings.llm.yandex
        if not cfg or not cfg.api_key:
            raise ValueError("Yandex LLM API key не настроен")
        if not cfg.folder_id or not str(cfg.folder_id).strip():
            raise ValueError("Yandex LLM folder_id не настроен")
        fid = str(cfg.folder_id).strip()
        model = normalize_yandex_resource_model_uri(model, fid)
        root = _yandex_openai_root(settings)
        auth = _yandex_auth_headers(api_key=str(cfg.api_key), folder_id=fid)
        return LLMClient(
            model=model,
            api_key=str(cfg.api_key).strip(),
            base_url=root,
            temperature=temp,
            max_tokens=resolved_max_tokens,
            timeout=timeout,
            default_headers=auth,
            llm_provider=actual_provider,
        )

    if actual_provider == "provider_litserve":
        cfg = settings.provider_litserve
        base_url = cfg.resolve_openai_v1_base_url()
        return LLMClient(
            model=model,
            api_key="litserve-local",
            base_url=base_url,
            temperature=temp,
            max_tokens=resolved_max_tokens,
            timeout=timeout,
            llm_provider=actual_provider,
        )

    if actual_provider == "custom_openai_compatible":
        # Этот провайдер всегда требует кастомный api_key + base_url; обычно
        # выбирается через ResolvedLLM из core.company_ai (custom:<id> в metadata).
        # Без явного api_key/base_url использование запрещено.
        raise ValueError(
            "custom_openai_compatible LLM требует явный api_key и base_url; "
            "вызывайте через core.company_ai.resolve_llm_for_capability(...)"
        )

    raise ValueError(f"Неизвестный LLM провайдер: {actual_provider}")


def _get_default_base_url(provider: str, settings: BaseSettings) -> str:
    """Возвращает base_url по умолчанию для провайдера."""
    if provider == "openrouter":
        return settings.llm.openrouter.base_url if settings.llm.openrouter else "https://openrouter.ai/api/v1"
    if provider == "bothub":
        return settings.llm.bothub.base_url if settings.llm.bothub else "https://bothub.chat/api/v2/openai/v1"
    if provider == "openai":
        return settings.llm.openai.base_url if settings.llm.openai else "https://api.openai.com/v1"
    if provider == "yandex":
        return _yandex_openai_root(settings)
    if provider == "provider_litserve":
        return settings.provider_litserve.resolve_openai_v1_base_url()
    return "https://api.openai.com/v1"


def get_llm_for_state(
    state: Optional["ExecutionState"] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    folder_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> LLMClient | MockLLM:
    """
    Создает LLM клиент с учётом mock конфига из state.
    
    Args:
        state: ExecutionState
        model_name: Имя модели
        temperature: Температура
        provider: Провайдер (openai, openrouter, bothub, provider_litserve, yandex)
        api_key: API ключ (напрямую или @var:my_key)
        base_url: Base URL провайдера (напрямую или @var:my_url)
        folder_id: Каталог Yandex Cloud при кастомном api_key / override
        max_tokens: Лимит токенов ответа для ноды
        
    Returns:
        MockLLM или реальный LLMClient
    """
    # Проверяем mock конфиг в state (без импорта apps.flows.src.mock)
    if state:
        mock_config = getattr(state, "mock", None)
        mock_responses = None
        if isinstance(mock_config, dict) and mock_config.get("enabled"):
            llm_responses = mock_config.get("llm")
            if llm_responses:
                mock_responses = llm_responses
        if mock_responses:
            mock = MockLLM(model_name=model_name or "mock-gpt-4")
            mock.configure(response_queue=mock_responses)
            return mock
    
    # Реальный LLM клиент
    return get_llm(
        model_name=model_name,
        temperature=temperature,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        folder_id=folder_id,
        max_tokens=max_tokens,
        state=state,
    )


def get_vision_llm(
    model_name: str = "google/gemini-2.5-flash-preview",
) -> "LLMClient | MockLLM":
    """Создает LLM клиент для vision запросов.

    В тестовом окружении (TESTING=true) возвращает тот же MockLLM, что и get_llm:
    модель подменяется на mock-gpt-4, реальный API не вызывается.
    """
    if _is_testing():
        mock_key = "mock-gpt-4"
        if mock_key not in _global_mock_registry:
            _global_mock_registry[mock_key] = MockLLM(model_name=mock_key)
        return _global_mock_registry[mock_key]

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

    if provider == "yandex":
        cfg = settings.llm.yandex
        if not cfg or not cfg.api_key:
            raise ValueError("Yandex LLM API key не настроен")
        if not cfg.folder_id or not str(cfg.folder_id).strip():
            raise ValueError("Yandex LLM folder_id не настроен")
        root = _yandex_openai_root(settings)
        auth = _yandex_auth_headers(api_key=str(cfg.api_key), folder_id=str(cfg.folder_id))
        model_norm = normalize_yandex_resource_model_uri(model_name, str(cfg.folder_id).strip())
        return LLMClient(
            model=model_norm,
            api_key=str(cfg.api_key).strip(),
            base_url=root,
            temperature=0.1,
            timeout=timeout,
            default_headers=auth,
            llm_provider=provider,
        )

    if provider == "provider_litserve":
        cfg = settings.provider_litserve
        return LLMClient(
            model=model_name,
            api_key="litserve-local",
            base_url=cfg.resolve_openai_v1_base_url(),
            temperature=0.1,
            timeout=timeout,
            llm_provider=provider,
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
