"""
TelegramChannelHandler - отправка сообщений через Telegram Bot API.
"""

import asyncio
import time
from typing import Unpack, override

import httpx

from apps.flows.src.models.enums import ChannelType
from core.config import get_settings
from core.http.client import HttpRequestKwargs, ProxyStrategy, request_with_strategy
from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object

from .base import BaseChannelHandler

logger = get_logger(__name__)

MESSAGE_DRAFT_MIN_INTERVAL_SEC = 0.08


async def _telegram_post(
    url: str,
    *,
    timeout: float,
    **kwargs: Unpack[HttpRequestKwargs],
) -> httpx.Response:
    """
    Исходящий POST к Telegram Bot API: DIRECT_FIRST (прямое соединение, затем egress proxy
    при ConnectTimeout/ConnectError, см. request_with_strategy).
    """
    return await request_with_strategy(
        "POST",
        url,
        strategy=ProxyStrategy.DIRECT_FIRST,
        timeout=timeout,
        **kwargs,
    )


def _parse_mode_for_plain_send(config: JsonObject) -> str | None:
    """
    Если ключ parse_mode отсутствует — HTML (обратная совместимость).
    Если задан null или пустая строка — без parse_mode (plain text).
    """
    if "parse_mode" not in config:
        return "HTML"
    raw = config.get("parse_mode")
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == "":
        return None
    return str(raw)


def get_telegram_api_base(config: JsonObject | None = None) -> str:
    """
    Возвращает базовый URL для Telegram API.

    Приоритет:
    1. config["api_base"] - для тестов
    2. TELEGRAM_API_BASE env - для тестов
    3. https://api.telegram.org - production
    """
    raw_api_base = config.get("api_base") if config is not None else None
    if isinstance(raw_api_base, str) and raw_api_base:
        return raw_api_base
    return get_settings().telegram.api_base


class TelegramChannelHandler(BaseChannelHandler):
    """
    Handler для отправки сообщений через Telegram Bot API.

    Поддерживаемые действия:
    - send_message: текстовое сообщение
    - send_photo: фото с опциональной подписью
    - send_document: документ/файл
    - reply: ответ на сообщение

    Конфигурация:
    {
        "bot_token": "@var:my_bot_token" или прямое значение,
        "parse_mode": "HTML" | "Markdown" | "MarkdownV2" | null | "" (null/пусто — plain, без поля в API),
        "disable_notification": false,
        "protect_content": false
    }
    """

    channel_type: ChannelType = ChannelType.TELEGRAM

    @override
    async def execute_action(
        self,
        action: str,
        params: JsonObject,
        config: JsonObject,
        variables: JsonObject,
    ) -> JsonObject:
        recipient = self._require_str_or_int_param(params, "recipient")
        if action == "send_message":
            text = self._require_str_param(params, "text")
            reply_to_message_id = self._optional_int_param(params, "reply_to_message_id")
            kwargs = self._extra_params(params, {"recipient", "text", "reply_to_message_id"})
            return await self.send_message(
                recipient=recipient,
                text=text,
                config=config,
                variables=variables,
                reply_to_message_id=reply_to_message_id,
                **kwargs,
            )
        if action == "send_photo":
            photo = self._require_file_param(params, "photo")
            caption = self._optional_str_param(params, "caption")
            reply_to_message_id = self._optional_int_param(params, "reply_to_message_id")
            kwargs = self._extra_params(
                params,
                {"recipient", "photo", "caption", "reply_to_message_id"},
            )
            return await self.send_photo(
                recipient=recipient,
                photo=photo,
                config=config,
                variables=variables,
                caption=caption,
                reply_to_message_id=reply_to_message_id,
                **kwargs,
            )
        if action == "send_document":
            document = self._require_file_param(params, "document")
            caption = self._optional_str_param(params, "caption")
            filename = self._optional_str_param(params, "filename")
            reply_to_message_id = self._optional_int_param(params, "reply_to_message_id")
            kwargs = self._extra_params(
                params,
                {"recipient", "document", "caption", "filename", "reply_to_message_id"},
            )
            return await self.send_document(
                recipient=recipient,
                document=document,
                config=config,
                variables=variables,
                caption=caption,
                filename=filename,
                reply_to_message_id=reply_to_message_id,
                **kwargs,
            )
        raise ValueError(
            f"Unknown action '{action}' for channel telegram. "
            + "Available: send_message, send_photo, send_document"
        )

    @override
    async def send_message(
        self,
        recipient: str | int,
        text: str,
        config: JsonObject,
        variables: JsonObject,
        reply_to_message_id: int | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """Отправляет текстовое сообщение в Telegram."""
        bot_token = self._get_bot_token(config, variables)
        url = f"{get_telegram_api_base(config)}/bot{bot_token}/sendMessage"

        payload: JsonObject = {
            "chat_id": recipient,
            "text": text,
        }
        pm = _parse_mode_for_plain_send(config)
        if pm is not None:
            payload["parse_mode"] = pm

        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        if config.get("disable_notification"):
            payload["disable_notification"] = True

        if config.get("protect_content"):
            payload["protect_content"] = True

        response = await _telegram_post(url, timeout=30.0, json=payload)
        try:
            result = parse_json_object(response.content, "telegram.sendMessage.response")
        finally:
            await response.aclose()

        if not result.get("ok"):
            logger.error(
                f"Telegram sendMessage failed: {result.get('description')}"
            )
            raise RuntimeError(
                f"Telegram API error: {result.get('description', 'Unknown error')}"
            )

        logger.info(f"Telegram message sent to {recipient}")
        return result

    async def send_message_draft(
        self,
        recipient: str,
        draft_id: int,
        text: str,
        config: JsonObject,
        variables: JsonObject,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> JsonObject:
        """
        Частичное обновление текста через Bot API sendMessageDraft (стриминг генерации).

        По документации Telegram метод ориентирован на приватные чаты. После серии вызовов
        отправьте итог через send_message.
        """
        if draft_id == 0:
            raise ValueError("draft_id must be non-zero")
        bot_token = self._get_bot_token(config, variables)
        url = f"{get_telegram_api_base(config)}/bot{bot_token}/sendMessageDraft"

        payload: JsonObject = {
            "chat_id": recipient,
            "draft_id": draft_id,
            "text": text,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        else:
            raw_parse_mode = config.get("parse_mode")
            if isinstance(raw_parse_mode, str) and raw_parse_mode:
                payload["parse_mode"] = raw_parse_mode
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id

        response = await _telegram_post(url, timeout=30.0, json=payload)
        try:
            result = parse_json_object(response.content, "telegram.sendMessageDraft.response")
        finally:
            await response.aclose()

        if not result.get("ok"):
            logger.error(
                "Telegram sendMessageDraft failed: %s",
                result.get("description"),
            )
            raise RuntimeError(
                f"Telegram API error: {result.get('description', 'Unknown error')}"
            )

        return result

    async def stream_message_draft_text(
        self,
        recipient: str,
        draft_id: int,
        accumulated_text: str,
        config: JsonObject,
        variables: JsonObject,
        *,
        last_sent_monotonic: list[float] | None = None,
        min_interval_sec: float = MESSAGE_DRAFT_MIN_INTERVAL_SEC,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> None:
        """
        Отправляет sendMessageDraft с троттлингом по времени (список из одного float —
        время последней успешной отправки, монотонные секунды).
        """
        now = time.monotonic()
        if last_sent_monotonic is None:
            last_sent_monotonic = [0.0]
        elapsed = now - last_sent_monotonic[0]
        if elapsed < min_interval_sec:
            await asyncio.sleep(min_interval_sec - elapsed)
        _ = await self.send_message_draft(
            recipient,
            draft_id,
            accumulated_text,
            config,
            variables,
            parse_mode=parse_mode,
            message_thread_id=message_thread_id,
        )
        last_sent_monotonic[0] = time.monotonic()

    @override
    async def send_photo(
        self,
        recipient: str | int,
        photo: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """Отправляет фото в Telegram."""
        bot_token = self._get_bot_token(config, variables)
        url = f"{get_telegram_api_base(config)}/bot{bot_token}/sendPhoto"

        if isinstance(photo, bytes):
            files = {"photo": ("photo.jpg", photo, "image/jpeg")}
            data: dict[str, str | int] = {"chat_id": recipient}

            if caption:
                data["caption"] = caption
                parse_mode = _parse_mode_for_plain_send(config)
                if parse_mode is not None:
                    data["parse_mode"] = parse_mode

            if reply_to_message_id:
                data["reply_to_message_id"] = reply_to_message_id

            response = await _telegram_post(url, timeout=60.0, data=data, files=files)
        else:
            payload: JsonObject = {
                "chat_id": recipient,
                "photo": photo,
            }

            if caption:
                payload["caption"] = caption
                parse_mode = _parse_mode_for_plain_send(config)
                if parse_mode is not None:
                    payload["parse_mode"] = parse_mode

            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id

            response = await _telegram_post(url, timeout=60.0, json=payload)

        try:
            result = parse_json_object(response.content, "telegram.sendPhoto.response")
        finally:
            await response.aclose()

        if not result.get("ok"):
            logger.error(f"Telegram sendPhoto failed: {result.get('description')}")
            raise RuntimeError(
                f"Telegram API error: {result.get('description', 'Unknown error')}"
            )

        logger.info(f"Telegram photo sent to {recipient}")
        return result

    @override
    async def send_document(
        self,
        recipient: str | int,
        document: str | bytes,
        config: JsonObject,
        variables: JsonObject,
        caption: str | None = None,
        filename: str | None = None,
        reply_to_message_id: int | None = None,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """Отправляет документ в Telegram."""
        bot_token = self._get_bot_token(config, variables)
        url = f"{get_telegram_api_base(config)}/bot{bot_token}/sendDocument"

        if isinstance(document, bytes):
            fname = filename or "document"
            files = {"document": (fname, document, "application/octet-stream")}
            data: dict[str, str | int] = {"chat_id": recipient}

            if caption:
                data["caption"] = caption
                parse_mode = _parse_mode_for_plain_send(config)
                if parse_mode is not None:
                    data["parse_mode"] = parse_mode

            if reply_to_message_id:
                data["reply_to_message_id"] = reply_to_message_id

            response = await _telegram_post(url, timeout=120.0, data=data, files=files)
        else:
            payload: JsonObject = {
                "chat_id": recipient,
                "document": document,
            }

            if caption:
                payload["caption"] = caption
                parse_mode = _parse_mode_for_plain_send(config)
                if parse_mode is not None:
                    payload["parse_mode"] = parse_mode

            if reply_to_message_id:
                payload["reply_to_message_id"] = reply_to_message_id

            response = await _telegram_post(url, timeout=120.0, json=payload)

        try:
            result = parse_json_object(response.content, "telegram.sendDocument.response")
        finally:
            await response.aclose()

        if not result.get("ok"):
            logger.error(
                f"Telegram sendDocument failed: {result.get('description')}"
            )
            raise RuntimeError(
                f"Telegram API error: {result.get('description', 'Unknown error')}"
            )

        logger.info(f"Telegram document sent to {recipient}")
        return result

    async def reply(
        self,
        recipient: str | int,
        message_id: int,
        text: str,
        config: JsonObject,
        variables: JsonObject,
        **kwargs: JsonValue,
    ) -> JsonObject:
        """Отвечает на сообщение (reply)."""
        return await self.send_message(
            recipient=recipient,
            text=text,
            config=config,
            variables=variables,
            reply_to_message_id=message_id,
            **kwargs,
        )

    def _get_bot_token(
        self,
        config: JsonObject,
        variables: JsonObject,
    ) -> str:
        """Извлекает bot_token из конфига или variables."""
        bot_token = config.get("bot_token") or config.get("_bot_token_resolved")

        if not isinstance(bot_token, str) or not bot_token:
            raise ValueError("bot_token is required for Telegram channel")

        if bot_token.startswith("@var:"):
            var_key = bot_token[5:]
            resolved = variables.get(var_key)
            if not isinstance(resolved, str) or not resolved:
                raise ValueError(f"Variable not found: {var_key}")
            return resolved

        return bot_token


__all__ = ["TelegramChannelHandler"]
