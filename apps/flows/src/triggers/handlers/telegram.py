"""
TelegramTriggerHandler - обработчик Telegram Bot webhook триггера.

Использует Telegram Bot API напрямую:
- setWebhook для регистрации
- deleteWebhook для снятия
- Верификация через secret_token
"""

import secrets
from typing import override

from apps.flows.config import get_settings as flows_get_settings
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.models import (
    TelegramBotApiBooleanResponse,
    TelegramTriggerConfig,
    TelegramUpdate,
    TriggerConfig,
    TriggerStatus,
    TriggerType,
)
from apps.flows.src.triggers.config_var_resolve import resolve_at_var_for_flow
from apps.flows.src.triggers.executor import TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from apps.flows.src.triggers.verify_draft import normalize_telegram_bot_token_for_api
from core.config import get_settings
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.types import JsonObject, require_json_object
from core.variables.resolver import VariableResolutionError

logger = get_logger(__name__)

_TELEGRAM_WEBHOOK_UPDATE_WHITELIST = frozenset({"message", "callback_query"})


class TelegramTriggerHandler(BaseTriggerHandler):
    """
    Handler для Telegram Bot webhook триггеров.

    Telegram конфиг:
    {
        "bot_token": "@var:my_bot_token",
        "allowed_users": [123456789],
        "allowed_chats": [],
        "commands": ["/start", "/help"],
        "allowed_updates": ["message", "callback_query"]
    }

    output_mapping по умолчанию (context — не variables):
    {
        "content": "@trigger:message.text",
        "context.chat_id": "@trigger:message.chat.id",
        "context.user_id": "@trigger:message.from.id",
        "context.username": "@trigger:message.from.username"
    }
    """

    trigger_type: TriggerType = TriggerType.TELEGRAM

    def __init__(self, base_url: str, *, container: FlowRuntimeContainer) -> None:
        super().__init__(base_url, container=container)
        self._executor: TriggerExecutor = TriggerExecutor()

    @override
    async def register(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig:
        """
        Регистрирует Telegram webhook.

        1. Извлекает bot_token из конфига
        2. Генерирует secret_token
        3. Вызывает setWebhook API
        """
        self._log_register(flow_id, trigger.trigger_id)

        config = TelegramTriggerConfig.model_validate(trigger.config)
        bot_token = config.bot_token

        if not bot_token:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message="bot_token is required",
            )

        bot_token_ref = bot_token.strip()
        if bot_token_ref.startswith("@var:"):
            bot_token_ref = await self._resolve_variable(bot_token_ref, flow_id, trigger.branch_id)
        bot_token = normalize_telegram_bot_token_for_api(bot_token_ref)
        if not bot_token:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message="bot_token is empty after resolve",
            )

        fs = flows_get_settings()
        if fs.server.env == "production":
            if not str(self.base_url).startswith("https://"):
                raise TriggerRegistrationError(
                    trigger_type="telegram",
                    flow_id=flow_id,
                    trigger_id=trigger.trigger_id,
                    message=(
                        "Telegram webhook base URL must be HTTPS in production. "
                        "Defaults to {platform_public_base_url}/flows; override via "
                        "server.flows_webhook_public_base_url or fix server.platform_public_base_url "
                        "/ ingress."
                    ),
                )

        # Генерируем secret_token для верификации
        secret_token = secrets.token_urlsafe(32)

        # Формируем webhook URL
        webhook_url = self.generate_webhook_url(flow_id, trigger.trigger_id)

        allowed_updates = TelegramTriggerHandler.normalize_allowed_updates(
            flow_id, trigger.trigger_id, config
        )
        api_url = f"{get_settings().telegram.api_base}/bot{bot_token}/setWebhook"

        payload = {
            "url": webhook_url,
            "secret_token": secret_token,
            "allowed_updates": allowed_updates,
            "drop_pending_updates": config.drop_pending_updates,
        }

        async with get_httpx_client(timeout=30.0, strategy=ProxyStrategy.SMART) as client:
            response = await client.post(api_url, json=payload)

            if response.status_code != 200:
                raise TriggerRegistrationError(
                    trigger_type="telegram",
                    flow_id=flow_id,
                    trigger_id=trigger.trigger_id,
                    message=f"Telegram API error: {response.status_code} - {response.text}",
                )

            result = TelegramBotApiBooleanResponse.model_validate_json(response.content)

            if not result.ok:
                description = result.description or "Telegram API returned ok=false"
                raise TriggerRegistrationError(
                    trigger_type="telegram",
                    flow_id=flow_id,
                    trigger_id=trigger.trigger_id,
                    message=f"Telegram API returned: {description}",
                )

        # Обновляем trigger с runtime данными
        trigger.webhook_url = webhook_url
        trigger.status = TriggerStatus.ACTIVE
        trigger.last_error = None

        # Сохраняем secret_token в config для верификации
        trigger.config["_secret_token"] = secret_token
        trigger.config["_bot_token_resolved"] = bot_token

        logger.info(
            "Telegram webhook registered: flow_id=%s, trigger=%s, url=%s",
            flow_id,
            trigger.trigger_id,
            webhook_url,
        )

        return trigger

    @override
    async def unregister(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> None:
        """
        Снимает Telegram webhook.
        """
        self._log_unregister(flow_id, trigger.trigger_id)

        config = TelegramTriggerConfig.model_validate(trigger.config)
        bot_token = config.bot_token_resolved or config.bot_token

        if not bot_token:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message="bot_token is required for unregister",
            )

        bot_token_ref = bot_token.strip()
        if bot_token_ref.startswith("@var:"):
            bot_token_ref = await self._resolve_variable(bot_token_ref, flow_id, trigger.branch_id)
        bot_token = normalize_telegram_bot_token_for_api(bot_token_ref)
        if not bot_token:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message="bot_token is empty after resolve",
            )

        api_url = f"{get_settings().telegram.api_base}/bot{bot_token}/deleteWebhook"

        async with get_httpx_client(timeout=30.0, strategy=ProxyStrategy.SMART) as client:
            response = await client.post(api_url, json={"drop_pending_updates": True})

        if response.status_code != 200:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message=f"Telegram deleteWebhook failed: {response.status_code} - {response.text}",
            )

        result = TelegramBotApiBooleanResponse.model_validate_json(response.content)
        if not result.ok:
            description = result.description or "Telegram API returned ok=false"
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message=f"Telegram deleteWebhook warning: {description}",
            )

        logger.info(
            "Telegram webhook deleted: flow_id=%s, trigger=%s",
            flow_id,
            trigger.trigger_id,
        )

    @override
    async def handle(
        self,
        flow_id: str,
        trigger_id: str,
        payload: JsonObject,
    ) -> JsonObject:
        """
        Обрабатывает входящий Telegram Update.

        1. Получает trigger конфиг
        2. Валидирует (allowed_users, commands)
        3. Запускает агента
        """
        flow_config = await self.container.flow_repository.get(flow_id)

        if not flow_config:
            raise TriggerValidationError(f"Flow not found: {flow_id}")

        trigger = flow_config.triggers.get(trigger_id)

        if not trigger:
            raise TriggerValidationError(f"Trigger not found: {trigger_id}")

        if not trigger.enabled:
            raise TriggerValidationError(f"Trigger is disabled: {trigger_id}")

        update = TelegramUpdate.model_validate(payload)
        trigger_payload = update.to_payload()
        await self._validate_update(trigger, update)

        exec_trigger = trigger.model_copy(deep=True)
        combined = {**dict(exec_trigger.input_mapping), **dict(exec_trigger.output_mapping)}
        if not combined:
            exec_trigger.output_mapping = self._default_mapping_for_update(update)

        result = await self._executor.execute(
            flow_id=flow_id,
            trigger=exec_trigger,
            payload=trigger_payload,
        )

        return result

    @staticmethod
    def normalize_allowed_updates(
        flow_id: str,
        trigger_id: str,
        config: TelegramTriggerConfig,
    ) -> list[str]:
        raw = config.allowed_updates
        ordered: list[str] = []
        for item in raw:
            if not item.strip():
                raise TriggerRegistrationError(
                    trigger_type="telegram",
                    flow_id=flow_id,
                    trigger_id=trigger_id,
                    message="allowed_updates entries must be non-empty strings",
                )
            name = item.strip()
            if name not in _TELEGRAM_WEBHOOK_UPDATE_WHITELIST:
                raise TriggerRegistrationError(
                    trigger_type="telegram",
                    flow_id=flow_id,
                    trigger_id=trigger_id,
                    message=(
                        f"Unsupported allowed_updates value {name!r}; "
                        f"allowed: {sorted(_TELEGRAM_WEBHOOK_UPDATE_WHITELIST)}"
                    ),
                )
            if name not in ordered:
                ordered.append(name)
        if not ordered:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger_id,
                message="allowed_updates cannot be empty",
            )
        return ordered

    async def _validate_update(
        self,
        trigger: TriggerConfig,
        update: TelegramUpdate,
    ) -> None:
        """Валидирует Telegram Update (message или callback_query)."""
        config = TelegramTriggerConfig.model_validate(trigger.config)

        cq = update.callback_query
        if cq is not None:
            callback_from_raw = cq.get("from")
            if callback_from_raw is None:
                raise TriggerValidationError("Telegram callback_query.from is required")
            callback_from = require_json_object(
                callback_from_raw,
                "telegram.callback_query.from",
            )
            msg_raw = cq.get("message")
            if msg_raw is None:
                raise TriggerValidationError("Telegram callback_query.message is required")
            msg = require_json_object(msg_raw, "telegram.callback_query.message")
            callback_chat_raw = msg.get("chat")
            if callback_chat_raw is None:
                raise TriggerValidationError("Telegram callback_query.message.chat is required")
            callback_chat = require_json_object(
                callback_chat_raw,
                "telegram.callback_query.message.chat",
            )
            user_id = callback_from.get("id")
            chat_id = callback_chat.get("id")
            if not isinstance(user_id, int):
                raise TriggerValidationError("Telegram callback_query.from.id must be int")
            if not isinstance(chat_id, int):
                raise TriggerValidationError("Telegram callback_query.message.chat.id must be int")
            data_raw = cq.get("data")
            data_str = data_raw if isinstance(data_raw, str) else None

            allowed_users = config.allowed_users
            if allowed_users and user_id not in allowed_users:
                raise TriggerValidationError(f"User {user_id} not allowed")

            allowed_chats = config.allowed_chats
            if allowed_chats and chat_id not in allowed_chats:
                raise TriggerValidationError(f"Chat {chat_id} not allowed")

            commands = config.commands
            if commands:
                if data_str is None:
                    raise TriggerValidationError("Telegram callback_query.data must be string")
                matched = any(data_str.startswith(cmd) for cmd in commands)
                if not matched:
                    raise TriggerValidationError(f"Command not matched for callback: {data_str!r}")
            return

        message = update.message
        if message is None:
            raise TriggerValidationError(
                "Telegram update must contain non-empty message or callback_query"
            )

        from_user_raw = message.get("from")
        if from_user_raw is None:
            raise TriggerValidationError("Telegram message.from is required")
        from_user = require_json_object(from_user_raw, "telegram.message.from")
        chat_raw = message.get("chat")
        if chat_raw is None:
            raise TriggerValidationError("Telegram message.chat is required")
        chat = require_json_object(chat_raw, "telegram.message.chat")
        text_raw = message.get("text")
        text = text_raw if isinstance(text_raw, str) else None

        user_id = from_user.get("id")
        chat_id = chat.get("id")
        if not isinstance(user_id, int):
            raise TriggerValidationError("Telegram message.from.id must be int")
        if not isinstance(chat_id, int):
            raise TriggerValidationError("Telegram message.chat.id must be int")

        allowed_users = config.allowed_users
        if allowed_users and user_id not in allowed_users:
            raise TriggerValidationError(f"User {user_id} not allowed")

        allowed_chats = config.allowed_chats
        if allowed_chats and chat_id not in allowed_chats:
            raise TriggerValidationError(f"Chat {chat_id} not allowed")

        commands = config.commands
        if commands:
            if text is None:
                raise TriggerValidationError("Telegram message.text must be string")
            matched = any(text.startswith(cmd) for cmd in commands)
            if not matched:
                raise TriggerValidationError(f"Command not matched: {text}")

    def _default_mapping_for_update(self, update: TelegramUpdate) -> dict[str, str]:
        """Дефолтный маппинг под тип Update."""
        if update.callback_query is not None:
            return {
                "content": "@trigger:callback_query.data",
                "context.chat_id": "@trigger:callback_query.message.chat.id",
                "context.user_id": "@trigger:callback_query.from.id",
                "context.username": "@trigger:callback_query.from.username",
                "context.message_id": "@trigger:callback_query.message.message_id",
                "context.callback_query_id": "@trigger:callback_query.id",
                "context.callback_data": "@trigger:callback_query.data",
            }
        return {
            "content": "@trigger:message.text",
            "context.chat_id": "@trigger:message.chat.id",
            "context.user_id": "@trigger:message.from.id",
            "context.username": "@trigger:message.from.username",
            "context.message_id": "@trigger:message.message_id",
        }

    async def _resolve_variable(self, var_ref: str, flow_id: str, branch_id: str) -> str:
        """Резолвит @var:key через тот же словарь, что у runtime flow (см. FlowFactory)."""
        try:
            return await resolve_at_var_for_flow(
                self.container.flow_factory,
                flow_id,
                var_ref,
                branch_id=branch_id,
            )
        except VariableResolutionError as e:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id="",
                message=str(e),
            ) from e

    def verify_secret_token(
        self,
        trigger: TriggerConfig,
        received_token: str | None,
    ) -> bool:
        """
        Сравнивает секрет из заголовка X-Telegram-Bot-Api-Secret-Token с сохранённым.

        При отсутствии ожидаемого или переданного токена возвращает False.
        """
        expected_token = trigger.config.get("_secret_token")
        if not expected_token:
            return False
        if not received_token:
            return False
        if not isinstance(expected_token, str):
            return False
        return secrets.compare_digest(expected_token, received_token)


__all__ = ["TelegramTriggerHandler"]
