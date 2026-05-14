"""
A2A Client - HTTP клиент для взаимодействия с внешними агентами.
Реализует A2A протокол.
Автоматически добавляет заголовки из контекста (Authorization, X-Company-Id и т.д.)
"""

import json
import uuid
from typing import Any, Dict, Optional

import httpx

from core.context import get_context
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)


def _extract_task_status_message(status_obj: Dict[str, Any]) -> Optional[str]:
    """Текст из A2A TaskStatus.message (строка или объект с parts)."""
    if not isinstance(status_obj, dict):
        return None
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

    pass


class A2AClient:
    """
    HTTP клиент для A2A протокола.
    Позволяет взаимодействовать с внешними агентами.
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def get_agent_card(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Получает agent-card.json от внешнего агента.

        Args:
            base_url: Базовый URL агента
            headers: Дополнительные HTTP-заголовки

        Returns:
            AgentCard как dict

        Raises:
            A2AClientError: При ошибке запроса
        """
        url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
        merged_headers = dict(headers or {})

        try:
            async with get_httpx_client(timeout=self.timeout) as client:
                response = await client.get(url, headers=merged_headers)

                if response.status_code != 200:
                    raise A2AClientError(f"Failed to get agent-card from {url}: {response.status_code}")

                return response.json()
        except httpx.HTTPError as e:
            raise A2AClientError(f"HTTP error getting agent card from {url}: {e}")
        except ValueError as e:
            raise A2AClientError(f"Invalid JSON response from {url}: {e}")

    async def send_task(
        self,
        base_url: str,
        content: str,
        session_id: Optional[str] = None,
        branch_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Отправляет задачу внешнему агенту.

        Args:
            base_url: Базовый URL агента
            content: Текст сообщения
            session_id: ID сессии (опционально)
            branch_id: ID ветки агента (в metadata уходит как `branch`)
            metadata: Дополнительные данные
            headers: Дополнительные HTTP-заголовки (до слияния с контекстом)
            timeout: Переопределение таймаута HTTP для этого запроса (секунды).

        Returns:
            Ответ агента

        Raises:
            A2AClientError: При ошибке запроса
        """
        # A2A endpoint без trailing slash
        url = base_url.rstrip('/')
        task_id = str(uuid.uuid4())
        session_id = session_id or str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": content}],
                    "messageId": str(uuid.uuid4()),
                },
                "configuration": {
                    "acceptedOutputModes": ["text"],
                },
            },
        }

        # Ветка skill/branch в A2A передаётся как metadata.branch (сервер: BaseChannel._prepare_task_params).
        final_metadata = metadata.copy() if metadata else {}
        if branch_id and branch_id != "default":
            final_metadata["branch"] = branch_id

        if final_metadata:
            payload["params"]["metadata"] = final_metadata

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
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            out_headers = {**request_headers, "Content-Type": "application/json"}
            async with get_httpx_client(timeout=effective_timeout, follow_redirects=True) as client:
                response = await client.post(url, content=body, headers=out_headers)

                if response.status_code != 200:
                    raise A2AClientError(
                        f"Failed to send task to {url}: {response.status_code} - {response.text}"
                    )

                result = response.json()

                if "error" in result:
                    raise A2AClientError(f"A2A error: {result['error']}")

                logger.debug(f"A2A response from {base_url}: {result}")

                # Нормализуем ответ - парсим artifacts в response
                return self._parse_a2a_response(result)
        except httpx.HTTPError as e:
            error_str = str(e) or type(e).__name__
            raise A2AClientError(f"HTTP error sending task to {url}: {error_str}")
        except ValueError as e:
            raise A2AClientError(f"Invalid JSON response from {url}: {e}")

    def _parse_a2a_response(self, raw_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Парсит A2A JSONRPC ответ и извлекает response из artifacts.

        Args:
            raw_response: Raw JSONRPC response

        Returns:
            Нормализованный ответ с полями response и status
        """
        # Извлекаем result из JSONRPC обёртки
        task_result = raw_response.get("result", raw_response)

        # Получаем статус
        status_obj = task_result.get("status", {})
        status = status_obj.get("state", "completed") if isinstance(status_obj, dict) else "completed"

        if status == "failed":
            error_msg = (
                _extract_task_status_message(status_obj)
                if isinstance(status_obj, dict)
                else None
            )
            raise A2AClientError(f"A2A task failed: {error_msg or 'unknown error'}")

        # Извлекаем текст из artifacts
        response_text = ""
        artifacts = task_result.get("artifacts", [])
        for artifact in artifacts:
            parts = artifact.get("parts", [])
            for part in parts:
                # Поддерживаем разные форматы: "type": "text" и "kind": "text"
                if part.get("type") == "text" or part.get("kind") == "text":
                    text = part.get("text", "")
                    if text:
                        response_text += text + "\n"
                elif part.get("type") == "data" or part.get("kind") == "data":
                    data = part.get("data")
                    if isinstance(data, dict) and "res" in data:
                        res_val = data["res"]
                        if isinstance(res_val, str) and res_val.strip():
                            response_text += res_val.strip() + "\n"

        return {
            "response": response_text.strip(),
            "status": status,
            "raw": raw_response,
        }

    async def check_health(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Проверяет доступность агента.

        Args:
            base_url: Базовый URL агента
            headers: Дополнительные HTTP-заголовки

        Returns:
            True если агент доступен
        """
        try:
            await self.get_agent_card(base_url, headers)
            return True
        except (A2AClientError, httpx.HTTPError, ValueError):
            return False
        except Exception as e:
            # Логируем неожиданные ошибки, но не даем им упасть
            logger.warning(f"Unexpected error checking health of {base_url}: {e}")
            return False
