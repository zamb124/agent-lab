"""WebhookChannelHandler — отправка сообщений через HTTP callback/webhook."""

import uuid
from typing import override

from a2a.types import Message, Part, Role, StreamResponse, TaskState, TaskStatusUpdateEvent
from google.protobuf.json_format import MessageToDict

from apps.flows.src.models.enums import ChannelType
from core.a2a import (
    a2a_task_state_to_platform,
    is_interrupted_a2a_task_state,
    is_terminal_a2a_task_state,
    make_task_status,
    platform_task_state_to_a2a,
    struct_from_mapping,
    value_from_json,
)
from core.http import get_httpx_client
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

from .base import BaseChannelHandler

logger = get_logger(__name__)

A2A_VERSION_HEADER = "A2A-Version"
A2A_PROTOCOL_VERSION = "1.0"

# Tool/channel event_type aliases → platform kebab TaskState.
_NOTIFICATION_EVENT_TO_PLATFORM: dict[str, str] = {
    "complete": "completed",
    "completed": "completed",
    "error": "failed",
    "failed": "failed",
    "working": "working",
    "submitted": "submitted",
    "canceled": "canceled",
    "cancelled": "canceled",
    "input-required": "input-required",
    "input_required": "input-required",
    "rejected": "rejected",
    "auth-required": "auth-required",
    "auth_required": "auth-required",
}


def _notification_event_to_platform_state(event_type: str) -> str:
    """event_type (alias / kebab / TASK_STATE_*) → platform kebab для A2A wire."""
    if not event_type:
        raise ValueError("webhook send_notification: event_type is required")
    if event_type in _NOTIFICATION_EVENT_TO_PLATFORM:
        return _NOTIFICATION_EVENT_TO_PLATFORM[event_type]
    if event_type.startswith("TASK_STATE_"):
        try:
            a2a_state = TaskState.Value(event_type)
        except ValueError as exc:
            raise ValueError(
                f"webhook send_notification: unknown A2A TaskState {event_type!r}"
            ) from exc
        return a2a_task_state_to_platform(a2a_state)
    allowed = sorted(_NOTIFICATION_EVENT_TO_PLATFORM)
    message = (
        "webhook send_notification: unknown event_type "
        + repr(event_type)
        + "; use platform kebab, TASK_STATE_*, or aliases "
        + repr(allowed)
    )
    raise ValueError(message)


class WebhookChannelHandler(BaseChannelHandler):
    """
    Handler для отправки через HTTP webhook/callback.

    Поддерживаемые действия:
    - send_message: POST с текстовым сообщением
    - send_payload: POST с произвольным JSON payload
    - send_notification: POST A2A Protocol 1.0 StreamResponse ProtoJSON (statusUpdate)

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
    async def execute_action(
        self,
        action: str,
        params: JsonObject,
        config: JsonObject,
        variables: JsonObject,
        state: ExecutionState | JsonObject | None = None,
    ) -> JsonObject:
        _ = state
        recipient = self._require_str_param(params, "recipient")
        if action == "send_payload":
            payload = require_json_object(params.get("payload"), "webhook.payload")
            return await self.send_payload(
                recipient=recipient,
                payload=payload,
                config=config,
                variables=variables,
            )
        if action == "send_notification":
            event_type = self._require_str_param(params, "event_type")
            data = require_json_object(params.get("data"), "webhook.notification.data")
            task_id = self._optional_str_param(params, "task_id")
            session_id = self._optional_str_param(params, "session_id")
            return await self.send_notification(
                recipient=recipient,
                event_type=event_type,
                data=data,
                config=config,
                variables=variables,
                task_id=task_id,
                session_id=session_id,
            )
        return await super().execute_action(
            action=action,
            params=params,
            config=config,
            variables=variables,
        )

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

        Аргументы:
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
        Отправляет A2A Protocol 1.0 push body: ProtoJSON ``StreamResponse``
        с ``statusUpdate`` (тот же канон, что Task Push Notification webhook).

        Аргументы:
            recipient: URL callback
            event_type: platform kebab / ``TASK_STATE_*`` / alias (complete→completed, error→failed)
            data: payload в ``status.message`` (text из ``response`` + Part.data)
            task_id: A2A ``taskId`` (обязателен)
            session_id: A2A ``contextId`` (обязателен; имя параметра channel tool)
        """
        _ = kwargs
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("webhook send_notification: task_id is required")
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError(
                "webhook send_notification: session_id is required (A2A contextId)"
            )

        platform_state = _notification_event_to_platform_state(event_type)
        a2a_state = platform_task_state_to_a2a(platform_state)

        parts: list[Part] = []
        response_value = data.get("response")
        if isinstance(response_value, str) and response_value.strip():
            parts.append(Part(text=response_value.strip()))
        parts.append(Part(data=value_from_json(data)))

        status = make_task_status(
            a2a_state,
            message=Message(
                message_id=str(uuid.uuid4()),
                role=Role.ROLE_AGENT,
                parts=parts,
            ),
        )
        event = TaskStatusUpdateEvent(
            task_id=task_id.strip(),
            context_id=session_id.strip(),
            status=status,
        )
        if is_terminal_a2a_task_state(a2a_state) or is_interrupted_a2a_task_state(a2a_state):
            # Platform extension (a2a.mdc): не поле wire proto TaskStatusUpdateEvent.
            event.metadata.CopyFrom(struct_from_mapping({"final": True}))

        stream = StreamResponse(status_update=event)
        payload = require_json_object(MessageToDict(stream), "StreamResponse")

        url = self._get_url(recipient, config, variables)
        headers = self._build_headers(config, variables)
        headers[A2A_VERSION_HEADER] = A2A_PROTOCOL_VERSION

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

        for key, value in config_headers.items():
            resolved_value = self._resolve_value(value, variables)
            if not isinstance(resolved_value, str):
                raise ValueError(f"webhook header {key!r} must resolve to a string")
            headers[key] = resolved_value

        return headers


__all__ = ["WebhookChannelHandler"]
