import json
import logging
from typing import Optional, Dict, Any

from app.interfaces.base import BaseInterface
from app.interfaces.telegram_interface import TelegramInterface
from app.interfaces.web_interface import WebInterface
from app.core.storage import Storage

logger = logging.getLogger(__name__)


class InterfaceFactory:
    """Фабрика для создания интерфейсов платформ"""

    def __init__(self):
        self.storage = Storage()

    async def create_interface(
        self, platform: str, config: Dict[str, Any]
    ) -> Optional[BaseInterface]:
        """Создает интерфейс для указанной платформы"""
        if platform == "telegram":
            return await self._create_telegram_interface(config)
        elif platform == "web":
            return WebInterface(config)
        elif platform == "api":
            # Для API не нужен интерфейс - результат уже в task.output_data
            return None
        else:
            raise ValueError(f"Неизвестная платформа: {platform}")

    async def _create_telegram_interface(
        self, config: Dict[str, Any]
    ) -> Optional[TelegramInterface]:
        """Создает Telegram интерфейс"""
        try:
            bot_username = config.get("bot_username")
            if not bot_username:
                logger.error("Нет bot_username для создания Telegram интерфейса")
                return None

            # Получаем токен из БД
            token_key = f"token:telegram:{bot_username}"
            token_json = await self.storage.get(token_key)

            if not token_json:
                logger.error(f"Не найден токен для бота {bot_username}")
                return None

            bot_token = json.loads(token_json)

            return TelegramInterface(bot_token, {"username": bot_username})

        except Exception as e:
            logger.error(f"Ошибка создания Telegram интерфейса: {e}")
            return None
