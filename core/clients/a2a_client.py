"""
A2A Client - HTTP клиент для взаимодействия с внешними агентами.
Реализует A2A протокол.
Автоматически добавляет заголовки из контекста (Authorization, X-Company-Id и т.д.)
"""

import uuid
from typing import Any, Dict, Optional

import httpx

from core.context import get_context
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)


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
        auth_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Получает agent-card.json от внешнего агента.

        Args:
            base_url: Базовый URL агента
            auth_headers: Заголовки авторизации

        Returns:
            AgentCard как dict

        Raises:
            A2AClientError: При ошибке запроса
        """
        url = f"{base_url.rstrip('/')}/.well-known/agent-card.json"
        headers = auth_headers or {}

        try:
            async with get_httpx_client(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)

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
        skill_id: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        auth_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Отправляет задачу внешнему агенту.

        Args:
            base_url: Базовый URL агента
            content: Текст сообщения
            session_id: ID сессии (опционально)
            skill_id: ID навыка агента
            metadata: Дополнительные данные
            auth_headers: Заголовки авторизации

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

        # Добавляем metadata с skill и переданными данными
        final_metadata = metadata.copy() if metadata else {}
        if skill_id and skill_id != "default":
            final_metadata["skill"] = skill_id
        
        if final_metadata:
            payload["params"]["metadata"] = final_metadata

        # Автоматически добавляем заголовки из контекста
        headers = auth_headers or {}
        context = get_context()
        if context:
            if context.auth_token and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {context.auth_token}"
            if context.active_company and "X-Company-Id" not in headers:
                headers["X-Company-Id"] = context.active_company.company_id
            if context.user and "X-User-Id" not in headers:
                headers["X-User-Id"] = context.user.user_id
            if context.trace_id and "X-Trace-Id" not in headers:
                headers["X-Trace-Id"] = context.trace_id
        
        logger.debug(f"A2A send_task to {url}: {content[:100]}...")

        try:
            async with get_httpx_client(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.post(url, json=payload, headers=headers)

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
            raise A2AClientError(f"HTTP error sending task to {url}: {e}")
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
        
        return {
            "response": response_text.strip(),
            "status": status,
            "raw": raw_response,
        }

    async def check_health(
        self,
        base_url: str,
        auth_headers: Optional[Dict[str, str]] = None,
    ) -> bool:
        """
        Проверяет доступность агента.

        Args:
            base_url: Базовый URL агента
            auth_headers: Заголовки авторизации

        Returns:
            True если агент доступен
        """
        try:
            await self.get_agent_card(base_url, auth_headers)
            return True
        except (A2AClientError, httpx.HTTPError, ValueError):
            return False
        except Exception as e:
            # Логируем неожиданные ошибки, но не даем им упасть
            logger.warning(f"Unexpected error checking health of {base_url}: {e}")
            return False
