"""
A2A Client - HTTP клиент для взаимодействия с внешними агентами.
Реализует A2A Protocol 1.0 (JSON-RPC).
Автоматически добавляет заголовки из контекста (Authorization, X-Company-Id и т.д.)
"""

import uuid

import httpx
from pydantic import Field

from core.a2a.methods import SEND_MESSAGE
from core.a2a.task_json import extract_text_from_parts_json, extract_text_from_task_json
from core.a2a.task_states import wire_task_state_to_platform
from core.context import get_context
from core.http import get_httpx_client
from core.logging import get_logger
from core.models import StrictBaseModel
from core.test_scope import TEST_SCOPE_HEADER, resolve_test_scope
from core.types import (
    JsonObject,
    parse_json_object,
    require_json_object,
)

logger = get_logger(__name__)

A2A_PROTOCOL_VERSION = "1.0"
A2A_VERSION_HEADER = "A2A-Version"


class A2ATaskResponse(StrictBaseModel):
    """Нормализованный ответ A2A `SendMessage`."""

    response: str = Field(..., description="Склеенный текст из text/data artifacts")
    status: str = Field(..., description="Platform kebab task status (из TASK_STATE_*)")
    raw: JsonObject = Field(..., description="Исходный JSON-RPC ответ A2A")


def _extract_task_status_message(status_obj: JsonObject) -> str | None:
    """Текст из A2A 1.0 TaskStatus.message.parts (ProtoJSON Part.text)."""
    message_value = status_obj.get("message")
    if not isinstance(message_value, dict):
        return None
    message = require_json_object(message_value, "A2A result.status.message")
    return extract_text_from_parts_json(message.get("parts"))


class A2AClientError(Exception):
    """Ошибка A2A клиента."""


class A2AClient:
    """
    HTTP клиент для A2A Protocol 1.0.
    Позволяет взаимодействовать с внешними агентами.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout: float = timeout

    async def get_agent_card(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
    ) -> JsonObject:
        """
        Получает agent-card.json от внешнего агента.

        Аргументы:
            base_url: Базовый URL агента
            headers: Дополнительные HTTP-заголовки

        Возвращает:
            AgentCard как dict

        Исключения:
            A2AClientError: При ошибке запроса
        """
        url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
        merged_headers = dict(headers or {})

        try:
            async with get_httpx_client(timeout=self.timeout) as client:
                response = await client.get(url, headers=merged_headers)

                if response.status_code != 200:
                    raise A2AClientError(f"Failed to get agent-card from {url}: {response.status_code}")

                return parse_json_object(response.content, "A2A agent-card")
        except httpx.HTTPError as e:
            raise A2AClientError(f"HTTP error getting agent card from {url}: {e}") from e
        except ValueError as e:
            raise A2AClientError(f"Invalid JSON response from {url}: {e}") from e

    async def send_task(
        self,
        base_url: str,
        content: str,
        session_id: str | None = None,
        branch_id: str = "default",
        metadata: JsonObject | None = None,
        headers: dict[str, str] | None = None,
        *,
        timeout: float | None = None,
    ) -> A2ATaskResponse:
        """
        Отправляет задачу внешнему агенту через `SendMessage`.

        Аргументы:
            base_url: Базовый URL агента
            content: Текст сообщения
            session_id: ID сессии (опционально)
            branch_id: ID ветки агента (в metadata уходит как `branch`)
            metadata: Дополнительные данные
            headers: Дополнительные HTTP-заголовки (до слияния с контекстом)
            timeout: Переопределение таймаута HTTP для этого запроса (секунды).

        Возвращает:
            Ответ агента

        Исключения:
            A2AClientError: При ошибке запроса
        """
        # A2A endpoint без завершающего слэша
        url = base_url.rstrip("/")
        task_id = str(uuid.uuid4())
        session_id = session_id or str(uuid.uuid4())

        message_payload: JsonObject = {
            "role": "ROLE_USER",
            "parts": [{"text": content}],
            "messageId": str(uuid.uuid4()),
            "contextId": session_id,
        }
        params_payload: JsonObject = {
            "message": message_payload,
            "configuration": {
                "acceptedOutputModes": ["text"],
            },
        }
        payload: JsonObject = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": SEND_MESSAGE,
            "params": params_payload,
        }

        # Ветка skill/branch в A2A передаётся как metadata.branch (сервер: BaseChannel._prepare_task_params).
        final_metadata: JsonObject = dict(metadata) if metadata is not None else {}
        if branch_id and branch_id != "default":
            final_metadata["branch"] = branch_id

        if final_metadata:
            params_payload["metadata"] = final_metadata

        # Автоматически добавляем заголовки из контекста
        request_headers = dict(headers or {})
        context = get_context()
        if context:
            if context.auth_token and "Authorization" not in request_headers:
                request_headers["Authorization"] = f"Bearer {context.auth_token}"
            if context.active_company and "X-Company-Id" not in request_headers:
                request_headers["X-Company-Id"] = context.active_company.company_id
            if context.user and "X-User-Id" not in request_headers:
                request_headers["X-User-Id"] = context.user.user_id
            if context.trace_id and "X-Trace-Id" not in request_headers:
                request_headers["X-Trace-Id"] = context.trace_id
            if context.language and "Accept-Language" not in request_headers:
                request_headers["Accept-Language"] = context.language.value

        test_scope = resolve_test_scope()
        if test_scope is not None and TEST_SCOPE_HEADER not in request_headers:
            request_headers[TEST_SCOPE_HEADER] = test_scope

        logger.debug(f"A2A send_task to {url}: {content[:100]}...")

        try:
            effective_timeout = self.timeout if timeout is None else timeout
            out_headers = {
                **request_headers,
                "Content-Type": "application/json",
                A2A_VERSION_HEADER: A2A_PROTOCOL_VERSION,
            }
            async with get_httpx_client(timeout=effective_timeout, follow_redirects=True) as client:
                response = await client.post(url, json=payload, headers=out_headers)

                if response.status_code != 200:
                    raise A2AClientError(
                        f"Failed to send task to {url}: {response.status_code} - {response.text}"
                    )

                result = parse_json_object(response.content, "A2A SendMessage response")

                if "error" in result:
                    raise A2AClientError(f"A2A error: {result['error']}")

                logger.debug(f"A2A response from {base_url}: {result}")

                # Нормализуем ответ — парсим artifacts в response
                return self._parse_a2a_response(result)
        except httpx.HTTPError as e:
            error_str = str(e) or type(e).__name__
            raise A2AClientError(f"HTTP error sending task to {url}: {error_str}") from e
        except ValueError as e:
            raise A2AClientError(f"Invalid JSON response from {url}: {e}") from e

    def _parse_a2a_response(self, raw_response: JsonObject) -> A2ATaskResponse:
        """
        Парсит A2A JSONRPC ответ и извлекает response из artifacts.

        Аргументы:
            raw_response: Raw JSONRPC response

        Возвращает:
            Нормализованный ответ с полями response и status
        """
        task_result_value = raw_response.get("result")
        task_result = (
            require_json_object(task_result_value, "A2A result")
            if task_result_value is not None
            else raw_response
        )

        status_value = task_result.get("status")
        if status_value is None:
            raise A2AClientError("A2A response missing result.status")
        status_obj = require_json_object(status_value, "A2A result.status")
        state_value = status_obj.get("state")
        if not isinstance(state_value, str) or not state_value:
            raise A2AClientError("A2A response missing result.status.state")
        try:
            status = wire_task_state_to_platform(state_value)
        except ValueError as e:
            raise A2AClientError(f"A2A response unknown result.status.state: {state_value!r}") from e

        if status == "failed":
            error_msg = _extract_task_status_message(status_obj)
            raise A2AClientError(f"A2A task failed: {error_msg or 'unknown error'}")

        try:
            response_text = extract_text_from_task_json(task_result)
        except ValueError:
            response_text = ""

        return A2ATaskResponse(
            response=response_text,
            status=status,
            raw=raw_response,
        )

    async def check_health(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
    ) -> bool:
        """
        Проверяет доступность агента.

        Аргументы:
            base_url: Базовый URL агента
            headers: Дополнительные HTTP-заголовки

        Возвращает:
            True если агент доступен
        """
        try:
            _ = await self.get_agent_card(base_url, headers)
            return True
        except (A2AClientError, httpx.HTTPError, ValueError):
            return False
        except Exception as e:
            # Логируем неожиданные ошибки, но не даём им упасть
            logger.warning(f"Unexpected error checking health of {base_url}: {e}")
            return False
