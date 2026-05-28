"""
A2A Client - HTTP клиент для взаимодействия с внешними агентами.
Реализует A2A протокол.
Автоматически добавляет заголовки из контекста (Authorization, X-Company-Id и т.д.)
"""

import uuid

import httpx
from pydantic import Field

from core.context import get_context
from core.http import get_httpx_client
from core.logging import get_logger
from core.models import StrictBaseModel
from core.types import (
    JsonObject,
    JsonValue,
    parse_json_object,
    require_json_array,
    require_json_object,
)

logger = get_logger(__name__)


class A2ATaskResponse(StrictBaseModel):
    """Нормализованный ответ A2A `message/send`."""

    response: str = Field(..., description="Склеенный текст из text/data artifacts")
    status: str = Field(..., description="A2A task status.state")
    raw: JsonObject = Field(..., description="Исходный JSON-RPC ответ A2A")


def _extract_task_status_message(status_obj: JsonObject) -> str | None:
    """Текст из A2A TaskStatus.message (строка или объект с parts)."""
    raw = status_obj.get("message")
    if raw is None:
        return None
    if isinstance(raw, str):
        stripped = raw.strip()
        return stripped if stripped else None
    if isinstance(raw, dict):
        parts = raw.get("parts")
        if not isinstance(parts, list):
            return None
        texts: list[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            root = part.get("root")
            if isinstance(root, dict):
                text = root.get("text")
                if isinstance(text, str) and text:
                    texts.append(text)
                continue
            text = part.get("text")
            if isinstance(text, str) and text:
                texts.append(text)
        joined = "".join(texts).strip()
        return joined if joined else None
    return None


class A2AClientError(Exception):
    """Ошибка A2A клиента."""


class A2AClient:
    """
    HTTP клиент для A2A протокола.
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
        Отправляет задачу внешнему агенту.

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
            "role": "user",
            "parts": [{"type": "text", "text": content}],
            "messageId": str(uuid.uuid4()),
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
            "method": "message/send",
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

        logger.debug(f"A2A send_task to {url}: {content[:100]}...")

        try:
            effective_timeout = self.timeout if timeout is None else timeout
            out_headers = {**request_headers, "Content-Type": "application/json"}
            async with get_httpx_client(timeout=effective_timeout, follow_redirects=True) as client:
                response = await client.post(url, json=payload, headers=out_headers)

                if response.status_code != 200:
                    raise A2AClientError(
                        f"Failed to send task to {url}: {response.status_code} - {response.text}"
                    )

                result = parse_json_object(response.content, "A2A message/send response")

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
        status = state_value

        if status == "failed":
            error_msg = _extract_task_status_message(status_obj)
            raise A2AClientError(f"A2A task failed: {error_msg or 'unknown error'}")

        response_text = ""
        artifacts_value = task_result.get("artifacts")
        artifacts = require_json_array(artifacts_value, "A2A result.artifacts") if artifacts_value is not None else []
        for artifact_value in artifacts:
            artifact = require_json_object(artifact_value, "A2A result.artifacts[]")
            parts_value = artifact.get("parts")
            if parts_value is None:
                raise A2AClientError("A2A artifact missing parts")
            parts = require_json_array(parts_value, "A2A artifact.parts")
            for part in parts:
                part_obj = require_json_object(part, "A2A artifact.parts[]")
                part_kind: JsonValue | None = part_obj.get("type")
                if part_kind is None:
                    part_kind = part_obj.get("kind")
                if part_kind == "text":
                    text = part_obj.get("text")
                    if isinstance(text, str) and text:
                        response_text += text + "\n"
                elif part_kind == "data":
                    data = part_obj.get("data")
                    if data is None:
                        continue
                    data_obj = require_json_object(data, "A2A data part")
                    res_value = data_obj.get("res")
                    if isinstance(res_value, str) and res_value.strip():
                        response_text += res_value.strip() + "\n"

        return A2ATaskResponse(
            response=response_text.strip(),
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
