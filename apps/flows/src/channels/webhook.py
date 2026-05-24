"""WebhookChannelHandler - отправка сообщений через HTTP callback/webhook."""

from typing import override

from apps.flows.src.models.enums import ChannelType
from core.http import get_httpx_client
from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

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

    channel_type: ChannelType = ChannelType.WEBHOOK

    @override
    async def send_message(
        self,
        recipient: str,
        text: str,
        config: JsonObject,
        variables: JsonObject,
        **kwargs: JsonValue,
    ) -> JsonObject:
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

        payload: JsonObject = {
            "type": "message",
            "text": text,
            **kwargs,
        }

        return await self._send_request(url, payload, headers, config)

    @override
    async def send_photo(
        self,
        recipient: str,
        photo: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """Отправляет фото через HTTP (как URL или base64)."""
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        photo_data = photo if isinstance(photo, str) else None

        payload: JsonObject = {
            "type": "photo",
            "photo_url": photo_data,
            "caption": caption,
            **kwargs,
        }

        return await self._send_request(url, payload, headers, config)

    @override
    async def send_document(
        self,
        recipient: str,
        document: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        filename: str | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """Отправляет документ через HTTP (как URL)."""
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        doc_data = document if isinstance(document, str) else None

        payload: JsonObject = {
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
        payload: JsonObject,
        config: JsonObject,
        variables: JsonObject,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """
        Отправляет произвольный JSON payload.

        Используется для гибких интеграций.
        """
        _ = kwargs
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        return await self._send_request(url, payload, headers, config)

    async def send_notification(
        self,
        recipient: str,
        event_type: str,
        data: JsonObject,
        config: JsonObject,
        variables: JsonObject,
        task_id: str | None = None,
        session_id: str | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """
        Отправляет нотификацию в A2A формате.

        Args:
            recipient: URL callback
            event_type: Тип события (complete, error, artifact, etc)
            data: Данные события
            task_id: ID задачи
            session_id: ID сессии
        """
        _ = kwargs
        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)

        payload: JsonObject = {
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
        payload: JsonObject,
        headers: dict[str, str],
        config: JsonObject,
    ) -> JsonObject:
        """Выполняет HTTP запрос."""
        raw_method = config.get("method", "POST")
        if not isinstance(raw_method, str) or not raw_method:
            raise ValueError("webhook config.method must be a non-empty string")
        method = raw_method.upper()

        raw_timeout = config.get("timeout", 30.0)
        if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, (int, float)):
            raise ValueError("webhook config.timeout must be a number")
        timeout = float(raw_timeout)

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

            return parse_json_object(response.content, "webhook.response")

    def _get_url(
        self,
        recipient: str,
        config: JsonObject,
        variables: JsonObject,
    ) -> str:
        """Определяет URL для отправки."""
        url = recipient or config.get("url")

        if not isinstance(url, str) or not url:
            raise ValueError("URL is required for webhook channel")

        resolved_url = self._resolve_value(url, variables)
        if not isinstance(resolved_url, str) or not resolved_url:
            raise ValueError("webhook URL must resolve to a non-empty string")
        return resolved_url

    def _build_headers(
        self,
        config: JsonObject,
        variables: JsonObject,
    ) -> dict[str, str]:
        """Строит заголовки с резолвингом переменных."""
        headers = {"Content-Type": "application/json"}

        raw_config_headers = config.get("headers")
        if raw_config_headers is None:
            config_headers = {}
        else:
            config_headers = require_json_object(raw_config_headers, "webhook.config.headers")

        raw_legacy_auth = config.get("auth_headers")
        if raw_legacy_auth is None:
            legacy_auth: JsonObject = {}
        else:
            legacy_auth = require_json_object(raw_legacy_auth, "webhook.config.auth_headers")

        if legacy_auth:
            merged_h = {**config_headers, **legacy_auth}
        else:
            merged_h = config_headers

        for key, value in merged_h.items():
            resolved_value = self._resolve_value(value, variables)
            if not isinstance(resolved_value, str):
                raise ValueError(f"webhook header {key!r} must resolve to a string")
            headers[key] = resolved_value

        return headers


__all__ = ["WebhookChannelHandler"]
