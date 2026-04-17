"""
TelegramTriggerHandler - обработчик Telegram Bot webhook триггера.

Использует Telegram Bot API напрямую:
- setWebhook для регистрации
- deleteWebhook для снятия
- Верификация через secret_token
"""

import secrets
from typing import Any, Dict

from apps.flows.src.models import TriggerConfig, TriggerStatus, TriggerType
from core.http import get_httpx_client
from apps.flows.src.triggers.executor import TriggerExecutor
from apps.flows.src.triggers.handlers.base import (
    BaseTriggerHandler,
    TriggerRegistrationError,
    TriggerValidationError,
)
from core.logging import get_logger

logger = get_logger(__name__)


class TelegramTriggerHandler(BaseTriggerHandler):
    """
    Handler для Telegram Bot webhook триггеров.
    
    Telegram конфиг:
    {
        "bot_token": "@var:my_bot_token",
        "allowed_users": [123456789],
        "allowed_chats": [],
        "commands": ["/start", "/help"]
    }
    
    Input mapping по умолчанию:
    {
        "content": "@trigger:message.text",
        "variables.chat_id": "@trigger:message.chat.id",
        "variables.user_id": "@trigger:message.from.id",
        "variables.username": "@trigger:message.from.username"
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
        
        # Резолвим @var:key если нужно
        if bot_token.startswith("@var:"):
            bot_token = await self._resolve_variable(bot_token)
        
        # Генерируем secret_token для верификации
        secret_token = secrets.token_urlsafe(32)
        
        # Формируем webhook URL
        webhook_url = self.generate_webhook_url(flow_id, trigger.trigger_id)
        
        # Определяем allowed_updates
        allowed_updates = ["message"]
        if config.get("commands"):
            allowed_updates = ["message"]
        
        from core.config import get_settings
        api_url = f"{get_settings().telegram.api_base}/bot{bot_token}/setWebhook"
        
        payload = {
            "url": webhook_url,
            "secret_token": secret_token,
            "allowed_updates": allowed_updates,
            "drop_pending_updates": config.get("drop_pending_updates", False),
        }
        
        async with get_httpx_client(timeout=30.0, proxy=True) as client:
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
        
        # Резолвим @var:key если нужно
        if bot_token.startswith("@var:"):
            bot_token = await self._resolve_variable(bot_token)
        
        from core.config import get_settings
        api_url = f"{get_settings().telegram.api_base}/bot{bot_token}/deleteWebhook"
        
        try:
            async with get_httpx_client(timeout=30.0, proxy=True) as client:
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
        
        # Применяем дефолтный input_mapping если не указан
        if not trigger.input_mapping:
            trigger.input_mapping = self._get_default_mapping()
        
        # Запускаем агента
        result = await self._executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload=payload,
        )
        
        return result
    
    async def _validate_update(
        self,
        trigger: TriggerConfig,
        payload: Dict[str, Any],
    ) -> None:
        """Валидирует Telegram Update."""
        config = trigger.config
        
        # Извлекаем данные из Update
        message = payload.get("message", {})
        from_user = message.get("from", {})
        chat = message.get("chat", {})
        text = message.get("text", "")
        
        user_id = from_user.get("id")
        chat_id = chat.get("id")
        
        # Проверяем allowed_users
        allowed_users = config.get("allowed_users", [])
        if allowed_users and user_id not in allowed_users:
            raise TriggerValidationError(f"User {user_id} not allowed")
        
        # Проверяем allowed_chats
        allowed_chats = config.get("allowed_chats", [])
        if allowed_chats and chat_id not in allowed_chats:
            raise TriggerValidationError(f"Chat {chat_id} not allowed")
        
        # Проверяем commands
        commands = config.get("commands", [])
        if commands:
            is_command_match = False
            for cmd in commands:
                if text.startswith(cmd):
                    is_command_match = True
                    break
            
            if not is_command_match:
                raise TriggerValidationError(f"Command not matched: {text}")
    
    def _get_default_mapping(self) -> Dict[str, str]:
        """Возвращает дефолтный input_mapping для Telegram."""
        return {
            "content": "@trigger:message.text",
            "variables.chat_id": "@trigger:message.chat.id",
            "variables.user_id": "@trigger:message.from.id",
            "variables.username": "@trigger:message.from.username",
            "variables.message_id": "@trigger:message.message_id",
        }
    
    async def _resolve_variable(self, var_ref: str) -> str:
        """Резолвит @var:key ссылку."""
        from apps.flows.src.container import get_container
        
        container = get_container()
        var_key = var_ref[5:]  # Убираем "@var:"
        
        value = await container.variables_service.get_var(var_key)
        
        if value is None:
            raise TriggerRegistrationError(
                trigger_type="telegram",
                flow_id="",
                trigger_id="",
                message=f"Variable not found: {var_key}",
            )
        
        return str(value)
    
    def verify_secret_token(
        self,
        trigger: TriggerConfig,
        received_token: str,
    ) -> bool:
        """
        Верифицирует secret_token из заголовка запроса.
        
        Args:
            trigger: Конфигурация триггера
            received_token: Токен из X-Telegram-Bot-Api-Secret-Token
            
        Returns:
            True если токен валидный
        """
        expected_token = trigger.config.get("_secret_token")
        
        if not expected_token:
            return True
        
        return secrets.compare_digest(expected_token, received_token)


__all__ = ["TelegramTriggerHandler"]
