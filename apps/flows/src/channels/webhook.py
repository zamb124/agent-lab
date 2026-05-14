"""
WebhookChannelHandler - отправка сообщений через HTTP callback/webhook.

Используется для:
- A2A нотификаций
- Callback в внешние системы
- Интеграции с любыми HTTP API
"""

from typing import Any, Dict, Optional, Union

from apps.flows.src.models.enums import ChannelType
from core.http import get_httpx_client
from core.logging import get_logger

from .base import BaseChannelHandler

logger = get_logger(__name__)


class WebhookChannelHandler(BaseChannelHandler):
    """
    Handler для отправки через HTTP webhook/callback.

    Поддерживаемые действия:
    - send_message: POST с текстовым сообщением
    - send_payload: POST с произвольным JSON payload
    - send_notification: POST в формате A2A нотификации

    Конфигурация:
    {
        "url": "https://example.com/callback" или "@var:callback_url",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer @var:api_key",
            "Content-Type": "application/json"
        },
        "timeout": 30
    }
    """

    channel_type = ChannelType.WEBHOOK

    async def send_message(
        self,
        recipient: str,
        text: str,
        config: Dict[str, Any],
        variables: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Отправляет текстовое сообщение через HTTP.

        Args:
            recipient: URL для отправки (или берется из config.url)
            text: Текст сообщения
            config: Конфигурация (url, headers, method)
            variables: Переменные для резолвинга
        """
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        payload = {
            "type": "message",
            "text": text,
            **kwargs,
        }

        return await self._send_request(url, payload, headers, config)

    async def send_photo(
        self,
        recipient: str,
        photo: Union[str, bytes],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        caption: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Отправляет фото через HTTP (как URL или base64)."""
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        photo_data = photo if isinstance(photo, str) else None

        payload = {
            "type": "photo",
            "photo_url": photo_data,
            "caption": caption,
            **kwargs,
        }

        return await self._send_request(url, payload, headers, config)

    async def send_document(
        self,
        recipient: str,
        document: Union[str, bytes],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Отправляет документ через HTTP (как URL)."""
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        doc_data = document if isinstance(document, str) else None

        payload = {
            "type": "document",
            "document_url": doc_data,
            "filename": filename,
            "caption": caption,
            **kwargs,
        }

        return await self._send_request(url, payload, headers, config)

    async def send_payload(
        self,
        recipient: str,
        payload: Dict[str, Any],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Отправляет произвольный JSON payload.

        Используется для гибких интеграций.
        """
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        return await self._send_request(url, payload, headers, config)

    async def send_notification(
        self,
        recipient: str,
        event_type: str,
        data: Dict[str, Any],
        config: Dict[str, Any],
        variables: Dict[str, Any],
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Отправляет нотификацию в A2A формате.

        Args:
            recipient: URL callback
            event_type: Тип события (complete, error, artifact, etc)
            data: Данные события
            task_id: ID задачи
            session_id: ID сессии
        """
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        payload = {
            "jsonrpc": "2.0",
            "method": "tasks/pushNotification",
            "params": {
                "id": task_id,
                "session_id": session_id,
                "event": {
                    "type": event_type,
                    "data": data,
                },
            },
        }

        return await self._send_request(url, payload, headers, config)

    async def _send_request(
        self,
        url: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Выполняет HTTP запрос."""
        method = config.get("method", "POST").upper()
        timeout = config.get("timeout", 30.0)

        async with get_httpx_client(timeout=timeout) as client:
            if method == "POST":
                response = await client.post(url, json=payload, headers=headers)
            elif method == "PUT":
                response = await client.put(url, json=payload, headers=headers)
            else:
                response = await client.post(url, json=payload, headers=headers)

            if response.status_code >= 400:
                logger.error(
                    f"Webhook request failed: {response.status_code} - {response.text}"
                )
                raise RuntimeError(
                    f"Webhook error: {response.status_code} - {response.text}"
                )

            logger.info(f"Webhook sent to {url}: {response.status_code}")

            try:
                return response.json()
            except Exception:
                return {"status": "ok", "status_code": response.status_code}

    def _get_url(
        self,
        recipient: str,
        config: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> str:
        """Определяет URL для отправки."""
        url = recipient or config.get("url")

        if not url:
            raise ValueError("URL is required for webhook channel")

        return self._resolve_value(url, variables)

    def _build_headers(
        self,
        config: Dict[str, Any],
        variables: Dict[str, Any],
    ) -> Dict[str, str]:
        """Строит заголовки с резолвингом переменных."""
        headers = {"Content-Type": "application/json"}

        config_headers = config.get("headers")
        if not isinstance(config_headers, dict):
            config_headers = {}
        legacy_auth = config.get("auth_headers")
        if isinstance(legacy_auth, dict) and len(legacy_auth) > 0:
            merged_h = {**config_headers, **legacy_auth}
        else:
            merged_h = dict(config_headers)
        for key, value in merged_h.items():
            headers[key] = self._resolve_value(value, variables)

        return headers


__all__ = ["WebhookChannelHandler"]
