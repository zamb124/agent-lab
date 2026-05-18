"""
LLM клиент.

Stream-first архитектура: LLM ВСЕГДА вызывается как stream.
ВСЕ ТИПЫ ИЗ a2a-sdk!
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Sequence
from contextlib import suppress
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

import httpx
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
from pydantic import BaseModel

from core.clients.llm.config import LLMCallConfig, ReasoningEffort
from core.clients.llm.logging import log_llm_stream_response
from core.clients.llm.openrouter_free_models import (
    OPENROUTER_FREE_MODELS_CACHE_KEY,
    OpenRouterFreeModelRecord,
    parse_openrouter_free_models,
)
from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.config.base import BaseSettings
from core.config.llm_openai_compat import yandex_llm_openai_root_from_provider_cfg
from core.config.openai_v1_base_url import normalize_openai_v1_base_url
from core.config.testing import is_testing as _is_testing
from core.http.client import ProxyStrategy, get_httpx_client
from core.http.egress_route_preference import (
    egress_prefer_proxy_set,
    normalized_http_origin,
)
from core.logging import get_logger
from core.variables import VariableResolutionError, VarResolver

if TYPE_CHECKING:
    from core.state import ExecutionState
from core.clients.llm.mock import (
    MockLLM,
    _global_mock_registry,
    get_global_mock_llm,
)
from core.clients.llm.model_routing import (
    HUMANITEC_LLM_PROVIDER,
    split_provider_prefixed_model,
)

logger = get_logger(__name__)

_CANDIDATE_COOLDOWN_UNTIL: dict[str, float] = {}
_openrouter_free_pool_redis: Any | None = None


class LLMStreamUserCancelledError(Exception):
    """Отмена flow во время чтения SSE; consumer закрыл HTTP stream (stream_cancel_poll)."""


class LLMStreamIdleTimeoutError(Exception):
    """SSE-стрим завис: ни одного чанка не получено за STREAM_IDLE_TIMEOUT_SECONDS.

    Причина — httpx aiter_lines() блокируется на неполной строке, когда
    OpenRouter отправляет SSE-данные без завершающего \\n в рамках одного
    TCP-пакета. Это интермиттентно (~каждый 2-й запрос) и зависит от
    балансировки серверов и нагрузки.
    """

    def __init__(self, idle_seconds: float, chunks_received: int):
        self.idle_seconds = idle_seconds
        self.chunks_received = chunks_received
        super().__init__(
            f"LLM stream idle timeout: no data for {idle_seconds:.1f}s "
            f"after {chunks_received} chunks received"
        )


# Максимальное время ожидания между чанками SSE-стрима (секунды).
# Данные показывают: нормальные чанки приходят за 3-5 секунд,
# зависание OpenRouter — стабильно после 16-18 чанков.
# 10 секунд — щедро для любой паузы модели, но не мучает пользователя.
STREAM_IDLE_TIMEOUT_SECONDS: float = 10.0

# Warning-порог: если между чанками > N секунд — логируем предупреждение.
_INTER_CHUNK_WARN_SECONDS: float = 5.0


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
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    }
                )
        elif isinstance(root, dict) and "file" in root:
            has_files = True
            file_obj = root["file"]
            if isinstance(file_obj, dict) and "bytes" in file_obj:
                mime_type = file_obj.get("mimeType") or file_obj.get("mime_type") or "image/png"
                b64_data = file_obj["bytes"]
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    }
                )

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


def _messages_to_openai(messages: Sequence[Message | Dict[str, Any] | str]) -> List[Dict[str, Any]]:
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
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=messages))],
            )
        ]

    if isinstance(messages, Message):
        return [messages]

    if isinstance(messages, dict):
        role = Role.user if messages.get("role", "user") == "user" else Role.agent
        content = messages.get("content", "")
        if not isinstance(content, str):
            raise ValueError("message.content must be string")
        return [
            Message(
                message_id=str(uuid.uuid4()),
                role=role,
                parts=[Part(root=TextPart(text=content))],
            )
        ]

    if isinstance(messages, list):
        if not messages:
            return []

        first = messages[0]

        if isinstance(first, str):
            string_messages: list[Message] = []
            for i, text in enumerate(messages):
                if not isinstance(text, str):
                    raise ValueError("messages list must contain only strings")
                role = Role.user if i % 2 == 0 else Role.agent
                string_messages.append(
                    Message(
                        message_id=str(uuid.uuid4()),
                        role=role,
                        parts=[Part(root=TextPart(text=text))],
                    )
                )
            return string_messages

        if isinstance(first, Message):
            typed_messages: list[Message] = []
            for msg in messages:
                if not isinstance(msg, Message):
                    raise ValueError("messages list must contain only Message objects")
                typed_messages.append(msg)
            return typed_messages

        if isinstance(first, dict):
            dict_messages: list[Message] = []
            for msg in messages:
                if not isinstance(msg, dict):
                    raise ValueError("messages list must contain only dict objects")
                role = Role.user if msg.get("role", "user") == "user" else Role.agent
                content = msg.get("content", "")
                if not isinstance(content, str):
                    raise ValueError("message.content must be string")
                dict_messages.append(
                    Message(
                        message_id=str(uuid.uuid4()),
                        role=role,
                        parts=[Part(root=TextPart(text=content))],
                    )
                )
            return dict_messages

    raise ValueError(f"Unsupported messages type: {type(messages)}")


def _candidate_key(candidate: LLMCallConfig) -> str:
    return f"{candidate.provider}:{candidate.base_url}:{candidate.model}"


def _is_humanitec_llm_provider(provider: Optional[str]) -> bool:
    return str(provider or "").strip() == HUMANITEC_LLM_PROVIDER


def _candidate_capability_metadata_is_strict(candidate: LLMCallConfig) -> bool:
    return candidate.source == "openrouter_free"


def _messages_have_non_text_parts(openai_messages: List[Dict[str, Any]]) -> bool:
    for message in openai_messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") != "text":
                return True
    return False


def _candidate_supports_request(
    candidate: LLMCallConfig,
    *,
    has_files: bool,
    has_tools: bool,
    has_response_format: bool,
) -> bool:
    # Empty metadata means "unknown" for explicit models. OpenRouter free-pool
    # records are discovery output, so absence of a capability there is treated
    # as unsupported for request-shaping features.
    strict_metadata = _candidate_capability_metadata_is_strict(candidate)
    if has_files and candidate.input_modalities and not (
        "image" in candidate.input_modalities or "file" in candidate.input_modalities
    ):
        return False
    if has_tools and (
        (strict_metadata and "tools" not in candidate.supported_parameters)
        or (candidate.supported_parameters and "tools" not in candidate.supported_parameters)
    ):
        return False
    if has_response_format and (
        (
            strict_metadata
            and "response_format" not in candidate.supported_parameters
            and "structured_outputs" not in candidate.supported_parameters
        )
        or (
            candidate.supported_parameters
            and "response_format" not in candidate.supported_parameters
            and "structured_outputs" not in candidate.supported_parameters
        )
    ):
        return False
    return True


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
        self.reasoning_effort = reasoning_effort
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
    ) -> List[LLMCallConfig]:
        candidates = list(self._static_candidates)
        if self._candidate_resolver is not None:
            try:
                resolved = await self._candidate_resolver()
                if resolved:
                    candidates = [
                        self._candidate_with_client_defaults(candidate)
                        for candidate in resolved
                    ]
            except Exception as exc:
                logger.warning(
                    "llm.candidates_resolver_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        has_files = _messages_have_non_text_parts(openai_messages)
        has_tools = bool(tools)
        has_response_format = bool(response_format)
        now = time.monotonic()
        filtered: list[LLMCallConfig] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = _candidate_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            cooldown_until = _CANDIDATE_COOLDOWN_UNTIL.get(key, 0.0)
            if cooldown_until > now:
                logger.info(
                    "llm.candidate_skipped_cooldown",
                    provider=candidate.provider,
                    model=candidate.model,
                    cooldown_left_seconds=round(cooldown_until - now, 1),
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
            filtered.append(candidate)
        if filtered:
            return filtered
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
        stream_cancel_poll: Optional[Callable[[], Awaitable[bool]]] = None,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Stream-first LLM call with universal candidate fallback.

        Fallback is only allowed before the first event is yielded to callers.
        Once any chunk/status has been emitted, the response belongs to that
        concrete model and failures propagate normally.
        """
        normalized_messages = _normalize_messages(messages)
        openai_messages = _messages_to_openai(normalized_messages)
        candidates = await self._resolve_candidates(
            openai_messages=openai_messages,
            tools=tools,
            response_format=response_format,
        )
        last_error: BaseException | None = None
        for idx, candidate in enumerate(candidates):
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
                        if idx > 0:
                            logger.info(
                                "llm.candidate_fallback_succeeded",
                                provider=candidate.provider,
                                model=candidate.model,
                                source=candidate.source,
                                attempt=idx + 1,
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
                    attempt=idx + 1,
                    remaining=len(candidates) - idx - 1,
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
                    attempt=idx + 1,
                    remaining=len(candidates) - idx - 1,
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
        reasoning_effort: Optional[str] = None,
        extra_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        stream_cancel_poll: Optional[Callable[[], Awaitable[bool]]] = None,
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

        logger.debug(
            f"LLM request: messages={len(openai_messages)}, tools={len(tools) if tools else 0}, response_format={bool(response_format)}"
        )
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
                    if response is None:
                        raise RuntimeError("LLM HTTP stream did not return a response")
                    if response.status_code != 200:
                        # Для stream response пытаемся прочитать тело ошибки
                        error_text = f"HTTP {response.status_code}"
                        try:
                            # Читаем первые байты ответа для получения деталей ошибки
                            error_chunks = []
                            async for chunk in response.aiter_bytes():
                                error_chunks.append(chunk)
                                if len(b"".join(error_chunks)) > 2000:  # Ограничиваем размер
                                    break
                            if error_chunks:
                                full_error = b"".join(error_chunks).decode("utf-8", errors="ignore")
                                # Пытаемся найти JSON в ответе
                                try:
                                    json_match = re.search(r"\{.*\}", full_error, re.DOTALL)
                                    if json_match:
                                        error_json = json.loads(json_match.group())
                                        error_text = json.dumps(
                                            error_json, indent=2, ensure_ascii=False
                                        )
                                    else:
                                        error_text = full_error[:1000]
                                except Exception:
                                    error_text = full_error[:1000]
                        except Exception as e:
                            logger.debug(f"Could not read error body: {e}")

                        logger.error(f"LLM API error {response.status_code}: {error_text}")
                        logger.error(f"Request URL: {self.base_url}/chat/completions")
                        logger.error(f"Request model: {self.model}")
                        logger.error(f"Request messages count: {len(openai_messages)}")
                        # Логируем первые и последние сообщения для отладки
                        if openai_messages:
                            logger.error(
                                f"First message role: {openai_messages[0].get('role')}, content length: {len(openai_messages[0].get('content', ''))}"
                            )
                            if len(openai_messages) > 1:
                                logger.error(
                                    f"Last message role: {openai_messages[-1].get('role')}, content length: {len(openai_messages[-1].get('content', ''))}"
                                )
                        response.raise_for_status()

                    cancelled_evt = asyncio.Event()
                    idle_timeout_evt = asyncio.Event()
                    # Shared mutable: watchdog обновляет/читает last_chunk_time
                    _last_chunk_time = time.monotonic()
                    _chunk_count = 0
                    watch: Optional[asyncio.Task[None]] = None

                    async def _watch_idle_and_cancel() -> None:
                        """Watchdog: отмена по poll + idle timeout."""
                        nonlocal _last_chunk_time
                        try:
                            while True:
                                await asyncio.sleep(1.0)
                                # 1. Проверяем отмену пользователем
                                if stream_cancel_poll is not None and await stream_cancel_poll():
                                    cancelled_evt.set()
                                    with suppress(Exception):
                                        await response.aclose()
                                    return
                                # 2. Проверяем idle timeout
                                idle = time.monotonic() - _last_chunk_time
                                idle_limit = (
                                    self.first_token_timeout
                                    if _chunk_count == 0
                                    else STREAM_IDLE_TIMEOUT_SECONDS
                                )
                                if idle >= idle_limit:
                                    logger.error(
                                        "LLM stream idle timeout: %.1fs without data, "
                                        "chunks_received=%d, model=%s",
                                        idle,
                                        _chunk_count,
                                        self.model,
                                    )
                                    idle_timeout_evt.set()
                                    with suppress(Exception):
                                        await response.aclose()
                                    return
                        except asyncio.CancelledError:
                            raise

                    # Watchdog запускается ВСЕГДА (не только при stream_cancel_poll)
                    watch = asyncio.create_task(_watch_idle_and_cancel())
                    try:
                        try:
                            async for line in response.aiter_lines():
                                # Обновляем время последнего чанка для watchdog
                                now = time.monotonic()
                                inter_chunk = now - _last_chunk_time
                                _last_chunk_time = now
                                _chunk_count += 1
                                if inter_chunk > _INTER_CHUNK_WARN_SECONDS:
                                    logger.warning(
                                        "LLM stream slow chunk: %.1fs gap before chunk #%d, "
                                        "model=%s",
                                        inter_chunk,
                                        _chunk_count,
                                        self.model,
                                    )
                                if not line.startswith("data: "):
                                    continue

                                data = line[6:]
                                if data == "[DONE]":
                                    break

                                chunk = json.loads(data)

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
                                            context_id=context_id,
                                            task_id=task_id,
                                            artifact=Artifact(
                                                artifact_id=str(uuid.uuid4()),
                                                parts=[Part(root=TextPart(text=mc))],
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
                                    logger.debug(f"LLM delta with reasoning fields: {delta}")

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
                                        f"LLM reasoning chunk: {len(reasoning_text)} chars"
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
                                                tool_calls_buffer[idx]["name"] = tc["function"][
                                                    "name"
                                                ]
                                            if tc["function"].get("arguments"):
                                                tool_calls_buffer[idx]["arguments"] += tc[
                                                    "function"
                                                ]["arguments"]
                        except Exception as e:
                            if cancelled_evt.is_set():
                                raise LLMStreamUserCancelledError() from e
                            if idle_timeout_evt.is_set():
                                # Учим SMART что этот origin надо через прокси:
                                # прямое соединение зависает mid-stream.
                                try:
                                    _origin = normalized_http_origin(
                                        f"{self.base_url}/chat/completions"
                                    )
                                    await egress_prefer_proxy_set(_origin)
                                    logger.info(
                                        "Marked origin %s for proxy preference "
                                        "(idle timeout after %d chunks)",
                                        _origin,
                                        _chunk_count,
                                    )
                                except Exception:
                                    pass
                                raise LLMStreamIdleTimeoutError(
                                    idle_seconds=(
                                        self.first_token_timeout
                                        if _chunk_count == 0
                                        else STREAM_IDLE_TIMEOUT_SECONDS
                                    ),
                                    chunks_received=_chunk_count,
                                ) from e
                            raise
                    finally:
                        if watch is not None:
                            watch.cancel()
                            with suppress(asyncio.CancelledError, RuntimeError):
                                await watch
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
                metadata={
                    "tool_calls": parsed_tool_calls,
                    "usage": usage_data,
                    "model": self.model,
                    "provider": self.llm_provider,
                    "source": self.llm_source,
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
                "model": self.model,
                "provider": self.llm_provider,
                "source": self.llm_source,
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
            "LLM stream complete: provider=%s, model=%s, source=%s, chunks=%d, content_len=%d, "
            "reasoning_len=%d, tool_calls=%d, duration=%.1fs",
            self.llm_provider,
            self.model,
            self.llm_source,
            _chunk_count,
            len(full_content),
            len(full_reasoning),
            len(tool_calls_buffer),
            stream_duration,
        )

        log_llm_stream_response(
            url=f"{self.base_url}/chat/completions",
            content=full_content,
            reasoning=full_reasoning if full_reasoning else None,
            tool_calls=list(tool_calls_buffer.values()) if tool_calls_buffer else None,
            usage=usage_data,
            provider=self.llm_provider,
            model=self.model,
            source=self.llm_source,
            duration_ms=stream_duration * 1000,
        )

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
        for idx, candidate in enumerate(candidates):
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
                    attempt=idx + 1,
                    remaining=len(candidates) - idx - 1,
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

        logger.info(
            f"LLM invoke: model={self.model}, messages={len(openai_messages)}, json_output={json_output}"
        )
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
                if event.artifact and event.artifact.name != "reasoning" and event.artifact.parts:
                    for part in event.artifact.parts:
                        root = part.root
                        if isinstance(root, TextPart):
                            content_parts.append(root.text)
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
            message_id=str(uuid.uuid4()),
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
        raise VariableResolutionError(f"Cannot resolve '{value}' without ExecutionState")
    resolved = VarResolver.resolve_ref(value, state.variables or {})
    if not isinstance(resolved, str):
        raise VariableResolutionError(f"Variable '{value}' for LLM config must resolve to string")
    if not resolved:
        raise VariableResolutionError(f"Variable '{value}' resolved to empty string")
    return resolved


def _resolve_headers_vars(
    headers: Optional[Dict[str, str]],
    state: Optional["ExecutionState"],
) -> Optional[Dict[str, str]]:
    if not headers:
        return None
    out: Dict[str, str] = {}
    for key, val in headers.items():
        resolved = _resolve_var(val, state)
        if resolved is None:
            continue
        out[key] = resolved
    return out


def _detect_provider(base_url: Optional[str]) -> Optional[str]:
    """Определяет провайдера по base_url."""
    if not base_url:
        return None
    if (
        "provider_litserve" in base_url
        or "localhost:8014" in base_url
        or "127.0.0.1:8014" in base_url
    ):
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


def _resolve_llm_call_config(
    config: LLMCallConfig,
    *,
    settings: BaseSettings,
    state: Optional["ExecutionState"] = None,
    inherit_transport_from: Optional[LLMCallConfig] = None,
    source: Optional[str] = None,
) -> LLMCallConfig:
    """Resolve one LLM config into a concrete runtime attempt.

    The input and output are the same model. This function only fills runtime
    transport fields from explicit config, inherited primary transport, or
    platform provider settings.
    """
    if not isinstance(config, LLMCallConfig):
        config = LLMCallConfig.model_validate(config)
    if not config.model or not str(config.model).strip():
        raise ValueError("LLM model обязателен")

    explicit_api_key = _resolve_var(config.api_key, state)
    explicit_base_url = _resolve_var(config.base_url, state)
    explicit_folder_id = _resolve_var(config.folder_id, state)
    inherit_transport = (
        inherit_transport_from is not None
        and config.provider is None
        and config.api_key is None
        and config.base_url is None
        and config.folder_id is None
    )
    actual_provider = (
        config.provider
        or (inherit_transport_from.provider if inherit_transport and inherit_transport_from else None)
        or _detect_provider(explicit_base_url)
        or settings.llm.provider
    )
    if not actual_provider:
        raise ValueError("LLM provider обязателен")

    candidate_api_key = (
        explicit_api_key
        if config.api_key is not None
        else (inherit_transport_from.api_key if inherit_transport and inherit_transport_from else None)
    )
    actual_base_url = (
        explicit_base_url
        if config.base_url is not None
        else (
            inherit_transport_from.base_url
            if inherit_transport and inherit_transport_from
            else _get_default_base_url(actual_provider, settings)
        )
    )
    folder_id = (
        explicit_folder_id
        if config.folder_id is not None
        else (inherit_transport_from.folder_id if inherit_transport and inherit_transport_from else None)
    )
    default_headers: Dict[str, str] = {}
    candidate_model = str(config.model).strip()
    resolved_source = source or config.source

    if candidate_api_key:
        if actual_provider == "custom_openai_compatible" and not actual_base_url:
            raise ValueError(
                "custom_openai_compatible: base_url обязателен (URL OpenAI-совместимого endpoint компании)"
            )
        if actual_provider == "openrouter" and settings.llm.openrouter:
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
            override_fid = str(folder_id).strip() if folder_id and str(folder_id).strip() else ""
            folder_id = override_fid or platform_fid
            if not folder_id:
                raise ValueError(
                    "Yandex LLM: задайте folder_id в переопределении ноды/ресурса "
                    "или llm.yandex.folder_id"
                )
            default_headers = _yandex_auth_headers(
                api_key=candidate_api_key,
                folder_id=folder_id,
            )
            candidate_model = normalize_yandex_resource_model_uri(candidate_model, folder_id)
            actual_base_url = normalize_openai_v1_base_url(str(actual_base_url).strip())
        return config.model_copy(
            update={
                "provider": actual_provider,
                "model": candidate_model,
                "api_key": candidate_api_key,
                "base_url": actual_base_url,
                "folder_id": folder_id,
                "default_headers": default_headers,
                "source": resolved_source,
                "extra_request_body": (
                    dict(config.extra_request_body) if config.extra_request_body else None
                ),
                "extra_request_headers": _resolve_headers_vars(
                    config.extra_request_headers,
                    state,
                ),
            }
        )

    provider_cfg = None
    if actual_provider == "openrouter":
        provider_cfg = settings.llm.openrouter
        if not provider_cfg or not provider_cfg.api_key:
            raise ValueError("OpenRouter API key не настроен")
        default_headers = {
            "HTTP-Referer": provider_cfg.site_url,
            "X-Title": provider_cfg.site_name,
        }
    elif actual_provider == "bothub":
        provider_cfg = settings.llm.bothub
        if not provider_cfg or not provider_cfg.api_key:
            raise ValueError("Bothub API key не настроен")
    elif actual_provider == "openai":
        provider_cfg = settings.llm.openai
        if not provider_cfg or not provider_cfg.api_key:
            raise ValueError("OpenAI API key не настроен")
    elif actual_provider == "yandex":
        provider_cfg = settings.llm.yandex
        if not provider_cfg or not provider_cfg.api_key:
            raise ValueError("Yandex LLM API key не настроен")
        if not provider_cfg.folder_id or not str(provider_cfg.folder_id).strip():
            raise ValueError("Yandex LLM folder_id не настроен")
        folder_id = str(provider_cfg.folder_id).strip()
        candidate_model = normalize_yandex_resource_model_uri(candidate_model, folder_id)
        default_headers = _yandex_auth_headers(api_key=str(provider_cfg.api_key), folder_id=folder_id)
    elif actual_provider == "provider_litserve":
        candidate_api_key = "litserve-local"
    elif actual_provider == "custom_openai_compatible":
        raise ValueError(
            "custom_openai_compatible LLM требует явный api_key и base_url; "
            "вызывайте через core.company_ai.resolve_llm_for_capability(...)"
        )
    else:
        raise ValueError(f"Неизвестный LLM провайдер: {actual_provider}")

    if provider_cfg is not None:
        candidate_api_key = str(provider_cfg.api_key).strip()
    return config.model_copy(
        update={
            "provider": actual_provider,
            "model": candidate_model,
            "api_key": candidate_api_key,
            "base_url": actual_base_url,
            "folder_id": folder_id,
            "default_headers": default_headers,
            "source": resolved_source,
            "extra_request_body": (
                dict(config.extra_request_body) if config.extra_request_body else None
            ),
            "extra_request_headers": _resolve_headers_vars(
                config.extra_request_headers,
                state,
            ),
        }
    )


def _resolved_llm_configs(
    primary: LLMCallConfig,
    fallback_models: Optional[List[LLMCallConfig]],
    *,
    settings: BaseSettings,
    state: Optional["ExecutionState"],
) -> list[LLMCallConfig]:
    resolved_primary = _resolve_llm_call_config(
        primary,
        settings=settings,
        state=state,
        source=primary.source,
    )
    resolved = [resolved_primary]
    for fallback in fallback_models or []:
        resolved.append(
            _resolve_llm_call_config(
                fallback,
                settings=settings,
                state=state,
                inherit_transport_from=resolved_primary,
                source="fallback",
            )
        )
    return resolved


def _candidate_from_openrouter_free_record(
    record: OpenRouterFreeModelRecord,
    *,
    settings: BaseSettings,
) -> LLMCallConfig:
    return _resolve_llm_call_config(
        LLMCallConfig(
            provider="openrouter",
            model=record.id,
            source="openrouter_free",
            supported_parameters=frozenset(record.supported_parameters),
            input_modalities=frozenset(record.input_modalities),
            output_modalities=frozenset(record.output_modalities),
            context_length=record.context_length,
        ),
        settings=settings,
        source="openrouter_free",
    )


async def _read_openrouter_free_records() -> list[OpenRouterFreeModelRecord]:
    global _openrouter_free_pool_redis

    if _openrouter_free_pool_redis is None:
        settings = get_settings()
        _openrouter_free_pool_redis = RedisClient(settings.database.redis_url)
    raw = await _openrouter_free_pool_redis.get(OPENROUTER_FREE_MODELS_CACHE_KEY)
    return parse_openrouter_free_models(raw)


def _platform_default_pool_is_configured(settings: BaseSettings) -> bool:
    return (
        settings.llm.openrouter_free_pool.enabled
        and settings.llm.openrouter is not None
        and bool(settings.llm.openrouter.api_key)
    )


def _should_use_platform_default_pool(
    *,
    model_name: Optional[str],
    provider: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    folder_id: Optional[str],
    settings: BaseSettings,
) -> bool:
    has_explicit_transport = any(
        value is not None and str(value).strip()
        for value in (api_key, base_url, folder_id)
    )
    explicit_humanitec_llm = _is_humanitec_llm_provider(provider)
    implicit_default_route = (
        model_name is None
        and provider is None
        and settings.llm.default_strategy == "openrouter_free_pool"
    )
    return (
        not has_explicit_transport
        and _platform_default_pool_is_configured(settings)
        and (explicit_humanitec_llm or implicit_default_route)
    )


def should_use_platform_default_free_pool(
    *,
    model_name: Optional[str],
    provider: Optional[str],
    api_key: Optional[str],
    base_url: Optional[str],
    folder_id: Optional[str],
    settings: BaseSettings,
) -> bool:
    """Public predicate for callers that must decide billing before creating a client."""
    return _should_use_platform_default_pool(
        model_name=model_name,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        folder_id=folder_id,
        settings=settings,
    )


def _make_platform_default_candidate_resolver(
    settings: BaseSettings,
    *,
    include_paid_fallback: bool,
) -> Callable[[], Awaitable[List[LLMCallConfig]]]:
    async def _resolve() -> List[LLMCallConfig]:
        candidates: list[LLMCallConfig] = []
        records = await _read_openrouter_free_records()
        for record in records:
            candidates.append(_candidate_from_openrouter_free_record(record, settings=settings))
        fallback_model = settings.llm.openrouter_free_pool.fallback_model.strip()
        if include_paid_fallback and fallback_model:
            candidates.append(
                _resolve_llm_call_config(
                    LLMCallConfig(
                        provider="openrouter",
                        model=fallback_model,
                        source="platform_paid_fallback",
                    ),
                    settings=settings,
                    source="platform_paid_fallback",
                )
            )
        return candidates

    return _resolve


def get_llm(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    folder_id: Optional[str] = None,
    max_tokens: Optional[int] = None,
    state: Optional["ExecutionState"] = None,
    fallback_models: Optional[List[LLMCallConfig]] = None,
    allow_platform_paid_fallback: bool = True,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    seed: Optional[int] = None,
    reasoning_effort: Optional[ReasoningEffort] = None,
    extra_request_body: Optional[Dict[str, Any]] = None,
    extra_request_headers: Optional[Dict[str, str]] = None,
) -> LLMClient | MockLLM:
    """
    Создает LLM клиент.

    Args:
        model_name: Имя модели
        temperature: Температура
        provider: Провайдер (openai, openrouter, bothub, provider_litserve, yandex,
            humanitec_llm)
        api_key: API ключ (напрямую или @var:my_key)
        base_url: Base URL провайдера (напрямую или @var:my_url)
        folder_id: Каталог Yandex Cloud (yandex); иначе из llm.yandex.folder_id
        max_tokens: Лимит токенов ответа (если None — из настроек модели / глобальных)
        state: ExecutionState для резолюции @var:
        fallback_models: Ordered list of full LLMCallConfig fallback attempts.
        allow_platform_paid_fallback: Для платформенного default-route через free-pool
            разрешает последний платный fallback. Рантайм flows выключает его при
            неположительном балансе, чтобы бесплатные модели не блокировались pre-flight биллингом.
    """
    settings = get_settings()
    _testing = _is_testing()

    split_prov, split_model = split_provider_prefixed_model(provider, model_name)
    if split_prov is not None:
        provider = split_prov
    model_name = split_model if split_model is not None else model_name

    if _should_use_platform_default_pool(
        model_name=model_name,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        folder_id=folder_id,
        settings=settings,
    ) and not _testing:
        fallback_model = settings.llm.openrouter_free_pool.fallback_model.strip()
        temp = temperature if temperature is not None else settings.llm.temperature
        resolved_max_tokens = max_tokens if max_tokens is not None else settings.llm.max_tokens
        primary = _resolve_llm_call_config(
            LLMCallConfig(
                provider="openrouter",
                model=fallback_model or settings.llm.default_model,
                temperature=temp,
                max_tokens=resolved_max_tokens,
                top_p=top_p,
                top_k=top_k,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                seed=seed,
                reasoning_effort=reasoning_effort,
                extra_request_body=extra_request_body,
                extra_request_headers=extra_request_headers,
                source="platform_paid_fallback",
            ),
            settings=settings,
            state=state,
            source="platform_paid_fallback",
        )
        return LLMClient(
            model=str(primary.model),
            api_key=str(primary.api_key),
            base_url=primary.base_url,
            temperature=temp,
            max_tokens=resolved_max_tokens,
            timeout=settings.llm.timeout,
            default_headers=dict(primary.default_headers),
            llm_provider=primary.provider,
            candidates=[primary] if allow_platform_paid_fallback else [],
            candidate_resolver=_make_platform_default_candidate_resolver(
                settings,
                include_paid_fallback=allow_platform_paid_fallback,
            ),
            first_token_timeout=settings.llm.openrouter_free_pool.first_token_timeout_seconds,
            candidate_cooldown_seconds=settings.llm.openrouter_free_pool.candidate_cooldown_seconds,
            platform_default_free_pool=True,
            platform_paid_fallback_enabled=allow_platform_paid_fallback,
            top_p=top_p,
            top_k=top_k,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            seed=seed,
            reasoning_effort=reasoning_effort,
            extra_request_body=extra_request_body,
            extra_request_headers=_resolve_headers_vars(extra_request_headers, state),
        )

    if _testing and _is_humanitec_llm_provider(provider):
        provider = None
        model_name = "mock-gpt-4"

    if _is_humanitec_llm_provider(provider):
        if any(
            value is not None and str(value).strip()
            for value in (api_key, base_url, folder_id)
        ):
            raise ValueError(
                "humanitec_llm: api_key/base_url/folder_id не задаются — это виртуальный "
                "провайдер платформы"
            )
        if not _platform_default_pool_is_configured(settings):
            raise ValueError(
                "humanitec_llm недоступен: включите llm.openrouter_free_pool и настройте "
                "llm.openrouter.api_key"
            )

    model = model_name or settings.llm.default_model
    if _testing and model and not model.startswith("mock-"):
        logger.warning(f"PYTEST detected: замена {model} на mock-gpt-4")
        model = "mock-gpt-4"

    if model.startswith("mock-"):
        if model not in _global_mock_registry:
            _global_mock_registry[model] = MockLLM(model_name=model)
        return _global_mock_registry[model]

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

    primary_config = LLMCallConfig(
        provider=provider,
        model=model,
        temperature=temp,
        max_tokens=resolved_max_tokens,
        api_key=api_key,
        folder_id=folder_id,
        base_url=base_url,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_body=extra_request_body,
        extra_request_headers=extra_request_headers,
        source="explicit",
    )
    candidates = _resolved_llm_configs(
        primary_config,
        fallback_models,
        settings=settings,
        state=state,
    )
    primary = candidates[0]

    if primary_config.api_key:
        logger.info(
            "[get_llm] Using custom api_key for provider=%s, base_url=%s",
            primary.provider,
            primary.base_url,
        )

    return LLMClient(
        model=str(primary.model),
        api_key=str(primary.api_key),
        base_url=primary.base_url,
        temperature=temp,
        max_tokens=resolved_max_tokens,
        timeout=timeout,
        default_headers=dict(primary.default_headers),
        llm_provider=primary.provider,
        candidates=candidates,
        first_token_timeout=settings.llm.openrouter_free_pool.first_token_timeout_seconds,
        candidate_cooldown_seconds=settings.llm.openrouter_free_pool.candidate_cooldown_seconds,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_body=extra_request_body,
        extra_request_headers=_resolve_headers_vars(extra_request_headers, state),
    )


def _get_default_base_url(provider: str, settings: BaseSettings) -> str:
    """Возвращает base_url по умолчанию для провайдера."""
    if provider == "openrouter":
        return (
            settings.llm.openrouter.base_url or "https://openrouter.ai/api/v1"
            if settings.llm.openrouter
            else "https://openrouter.ai/api/v1"
        )
    if provider == "bothub":
        return (
            settings.llm.bothub.base_url or "https://bothub.chat/api/v2/openai/v1"
            if settings.llm.bothub
            else "https://bothub.chat/api/v2/openai/v1"
        )
    if provider == "openai":
        return (
            settings.llm.openai.base_url or "https://api.openai.com/v1"
            if settings.llm.openai
            else "https://api.openai.com/v1"
        )
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
    fallback_models: Optional[List[LLMCallConfig]] = None,
    allow_platform_paid_fallback: bool = True,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    seed: Optional[int] = None,
    reasoning_effort: Optional[ReasoningEffort] = None,
    extra_request_body: Optional[Dict[str, Any]] = None,
    extra_request_headers: Optional[Dict[str, str]] = None,
) -> LLMClient | MockLLM:
    """
    Создает LLM клиент с учётом mock конфига из state.

    Args:
        state: ExecutionState
        model_name: Имя модели
        temperature: Температура
        provider: Провайдер (openai, openrouter, bothub, provider_litserve, yandex,
            humanitec_llm)
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
        fallback_models=fallback_models,
        allow_platform_paid_fallback=allow_platform_paid_fallback,
        top_p=top_p,
        top_k=top_k,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        seed=seed,
        reasoning_effort=reasoning_effort,
        extra_request_body=extra_request_body,
        extra_request_headers=extra_request_headers,
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
    _ = get_llm(model_name)
    mock_llm = get_global_mock_llm(model_name)
    if mock_llm is None:
        raise RuntimeError(f"Mock LLM не зарегистрирован: {model_name}")

    mock_llm.reset()
    mock_llm.configure(
        response_queue=response_queue,
        tool_responses=tool_responses,
        responses=responses,
        default_response=default_response,
    )

    return mock_llm
