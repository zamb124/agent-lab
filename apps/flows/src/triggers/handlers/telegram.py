"""
TelegramTriggerHandler - обработчик Telegram Bot webhook триггера.

Использует Telegram Bot API напрямую:
- setWebhook для регистрации
- deleteWebhook для снятия
- Верификация через secret_token
"""

import secrets
from typing import Any, Dict, List, Optional

from apps.flows.config import get_settings as flows_get_settings
from apps.flows.src.models import TriggerConfig, TriggerStatus, TriggerType
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

    trigger_type = TriggerType.TELEGRAM

    def __init__(self, base_url: str):
        super().__init__(base_url)
        self._executor = TriggerExecutor()

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

        config = trigger.config
        bot_token = config.get("bot_token")

        if not bot_token:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger.trigger_id,
                message="bot_token is required",
            )

        if isinstance(bot_token, str) and bot_token.strip().startswith("@var:"):
            bot_token = await self._resolve_variable(bot_token.strip(), flow_id, trigger.branch_id)
        bot_token = normalize_telegram_bot_token_for_api(str(bot_token))
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
            "drop_pending_updates": config.get("drop_pending_updates", False),
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

            result = response.json()

            if not result.get("ok"):
                raise TriggerRegistrationError(
                    trigger_type="telegram",
                    flow_id=flow_id,
                    trigger_id=trigger.trigger_id,
                    message=f"Telegram API returned: {result.get('description', 'Unknown error')}",
                )

        # Обновляем trigger с runtime данными
        trigger.webhook_url = webhook_url
        trigger.status = TriggerStatus.ACTIVE
        trigger.last_error = None

        # Сохраняем secret_token в config для верификации
        trigger.config["_secret_token"] = secret_token
        trigger.config["_bot_token_resolved"] = bot_token

        logger.info(
            f"Telegram webhook registered: flow_id={flow_id}, "
            f"trigger={trigger.trigger_id}, url={webhook_url}"
        )

        return trigger

    async def unregister(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> None:
        """
        Снимает Telegram webhook.
        """
        self._log_unregister(flow_id, trigger.trigger_id)

        config = trigger.config
        bot_token = config.get("_bot_token_resolved") or config.get("bot_token")

        if not bot_token:
            logger.warning(
                f"No bot_token for unregister: flow_id={flow_id}, "
                f"trigger={trigger.trigger_id}"
            )
            return

        if isinstance(bot_token, str) and bot_token.strip().startswith("@var:"):
            bot_token = await self._resolve_variable(bot_token.strip(), flow_id, trigger.branch_id)
        bot_token = normalize_telegram_bot_token_for_api(str(bot_token))
        if not bot_token:
            logger.warning(
                f"No usable bot_token for unregister: flow_id={flow_id}, "
                f"trigger={trigger.trigger_id}"
            )
            return

        from core.config import get_settings
        api_url = f"{get_settings().telegram.api_base}/bot{bot_token}/deleteWebhook"

        try:
            async with get_httpx_client(timeout=30.0, strategy=ProxyStrategy.SMART) as client:
                response = await client.post(api_url, json={"drop_pending_updates": True})

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        logger.info(
                            f"Telegram webhook deleted: flow_id={flow_id}, "
                            f"trigger={trigger.trigger_id}"
                        )
                    else:
                        logger.warning(
                            f"Telegram deleteWebhook warning: {result.get('description')}"
                        )
                else:
                    logger.warning(
                        f"Telegram deleteWebhook failed: {response.status_code}"
                    )
        except Exception as e:
            logger.error(f"Error deleting Telegram webhook: {e}")

    async def handle(
        self,
        flow_id: str,
        trigger_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Обрабатывает входящий Telegram Update.

        1. Получает trigger конфиг
        2. Валидирует (allowed_users, commands)
        3. Запускает агента
        """
        from apps.flows.src.container import get_container

        container = get_container()
        flow_config = await container.flow_repository.get(flow_id)

        if not flow_config:
            raise TriggerValidationError(f"Flow not found: {flow_id}")

        trigger = flow_config.triggers.get(trigger_id)

        if not trigger:
            raise TriggerValidationError(f"Trigger not found: {trigger_id}")

        if not trigger.enabled:
            raise TriggerValidationError(f"Trigger is disabled: {trigger_id}")

        # Валидируем payload
        await self._validate_update(trigger, payload)

        exec_trigger = trigger.model_copy(deep=True)
        combined = {**dict(exec_trigger.input_mapping), **dict(exec_trigger.output_mapping)}
        if not combined:
            exec_trigger.input_mapping = self._default_mapping_for_payload(payload)

        result = await self._executor.execute(
            flow_id=flow_id,
            trigger=exec_trigger,
            payload=payload,
        )

        return result

    @staticmethod
    def normalize_allowed_updates(
        flow_id: str,
        trigger_id: str,
        config: Dict[str, Any],
    ) -> List[str]:
        raw = config.get("allowed_updates")
        if raw is None:
            return ["message"]
        if not isinstance(raw, list):
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id=flow_id,
                trigger_id=trigger_id,
                message="allowed_updates must be a list of strings",
            )
        ordered: List[str] = []
        for item in raw:
            if not isinstance(item, str) or not item.strip():
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
        payload: Dict[str, Any],
    ) -> None:
        """Валидирует Telegram Update (message или callback_query)."""
        config = trigger.config

        cq = payload.get("callback_query")
        if isinstance(cq, dict) and cq:
            from_user = cq.get("from") if isinstance(cq.get("from"), dict) else {}
            msg = cq.get("message") if isinstance(cq.get("message"), dict) else {}
            chat = msg.get("chat") if isinstance(msg.get("chat"), dict) else {}
            user_id = from_user.get("id")
            chat_id = chat.get("id")
            data = cq.get("data")
            data_str = data if isinstance(data, str) else ""

            allowed_users = config.get("allowed_users", [])
            if allowed_users and user_id not in allowed_users:
                raise TriggerValidationError(f"User {user_id} not allowed")

            allowed_chats = config.get("allowed_chats", [])
            if allowed_chats and chat_id not in allowed_chats:
                raise TriggerValidationError(f"Chat {chat_id} not allowed")

            commands = config.get("commands", [])
            if commands:
                matched = any(data_str.startswith(cmd) for cmd in commands)
                if not matched:
                    raise TriggerValidationError(f"Command not matched for callback: {data_str!r}")
            return

        message = payload.get("message")
        if not isinstance(message, dict) or not message:
            raise TriggerValidationError(
                "Telegram update must contain non-empty message or callback_query"
            )

        from_user = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        text_raw = message.get("text", "")
        text = text_raw if isinstance(text_raw, str) else ""

        user_id = from_user.get("id")
        chat_id = chat.get("id")

        allowed_users = config.get("allowed_users", [])
        if allowed_users and user_id not in allowed_users:
            raise TriggerValidationError(f"User {user_id} not allowed")

        allowed_chats = config.get("allowed_chats", [])
        if allowed_chats and chat_id not in allowed_chats:
            raise TriggerValidationError(f"Chat {chat_id} not allowed")

        commands = config.get("commands", [])
        if commands:
            matched = any(text.startswith(cmd) for cmd in commands)
            if not matched:
                raise TriggerValidationError(f"Command not matched: {text}")

    def _default_mapping_for_payload(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """Дефолтный маппинг под тип Update."""
        cq = payload.get("callback_query")
        if isinstance(cq, dict) and cq:
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
        from apps.flows.src.container import get_container
        from apps.flows.src.triggers.config_var_resolve import resolve_at_var_for_flow
        from core.variables.resolver import VariableResolutionError

        container = get_container()
        try:
            return await resolve_at_var_for_flow(
                container,
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
        received_token: Optional[str],
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
        return secrets.compare_digest(str(expected_token), str(received_token))


__all__ = ["TelegramTriggerHandler"]
