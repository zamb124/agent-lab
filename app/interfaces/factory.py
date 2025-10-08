import json
import logging
from typing import Optional, Dict, Any

from app.interfaces.base import BaseInterface
from app.interfaces.telegram_interface import TelegramInterface
from app.interfaces.amocrm_interface import AmoCRMInterface
from app.interfaces.web_interface import WebInterface
from app.interfaces.api_interface import APIInterface
from app.core.storage import Storage
from app.models import FlowConfig

logger = logging.getLogger(__name__)


class InterfaceFactory:
    """Фабрика для создания и регистрации интерфейсов платформ"""

    PLATFORM_INTERFACES = {
        "telegram": TelegramInterface,
        "web": WebInterface,
        "api": APIInterface,
    }

    def __init__(self):
        self.storage = Storage()

    async def create_interface(
        self, platform: str, config: Dict[str, Any]
    ) -> Optional[BaseInterface]:
        """Создает интерфейс для указанной платформы"""
        if platform == "amocrm":
            return await self._create_amocrm_interface(config)
        elif platform == "telegram":
            # Получаем flow_id из метаданных
            flow_id = config.get("flow_id")

            if not flow_id:
                logger.error("Нет flow_id для создания Telegram интерфейса")
                return None

            # Загружаем flow config чтобы получить telegram_config
            flow_config = await self.storage.get_flow_config(flow_id)
            if not flow_config:
                logger.error(f"Flow {flow_id} не найден")
                return None

            telegram_config = flow_config.platforms.get("telegram")
            if not telegram_config:
                logger.error(f"Flow {flow_id} не имеет telegram платформы")
                return None

            # Получаем токен через новый способ (поддерживает @var:key)
            bot_token = await TelegramInterface.get_bot_token_for_flow(flow_id, telegram_config)
            if not bot_token:
                logger.error(f"Не найден токен для flow {flow_id}")
                return None

            return TelegramInterface(bot_token, telegram_config)
        elif platform == "web":
            return WebInterface(config)
        elif platform == "api":
            # Для API не нужен интерфейс - результат уже в task.output_data
            return None
        else:
            interface_class = self.PLATFORM_INTERFACES.get(platform)
            if not interface_class:
                raise ValueError(f"Неизвестная платформа: {platform}")
            return interface_class(config)
    async def _create_amocrm_interface(
        self, config: Dict[str, Any]
    ) -> Optional[AmoCRMInterface]:
        """Создает AmoCRM интерфейс"""
        try:
            scope_id = config.get("scope_id")
            subdomain = config.get("subdomain")

            if not scope_id:
                logger.error("Нет scope_id для создания AmoCRM интерфейса")
                return None

            if not subdomain:
                logger.error("Нет subdomain для создания AmoCRM интерфейса")
                return None

            platform_config = {
                "subdomain": subdomain,
                "scope_id": scope_id,
            }

            # Добавляем дополнительные данные из config если есть
            for key in ["chat_id", "contact_id", "author_name"]:
                if key in config:
                    platform_config[key] = config[key]

            return AmoCRMInterface(scope_id, subdomain)

        except Exception as e:
            logger.error(f"Ошибка создания AmoCRM интерфейса: {e}", exc_info=True)
            return None

    async def register_platform(
        self,
        platform: str,
        username: str,
        flow_id: str = None
    ) -> Dict[str, Any]:
        """
        Регистрирует платформу (настраивает webhook, polling, commands)

        Args:
            platform: Название платформы (telegram, whatsapp, discord...)
            username: Username бота на платформе
            flow_id: ID конкретного flow (если None - регистрирует для всех)

        Returns:
            Результат регистрации
        """
        interface_class = self.PLATFORM_INTERFACES.get(platform)
        if not interface_class:
            raise ValueError(f"Unknown platform: {platform}")

        if not hasattr(interface_class, 'register'):
            logger.info(f"📋 Платформа {platform} не требует регистрации")
            return {"success": True, "platform": platform, "registered": False}

        # Находим все flow с этой платформой и username
        flows_to_register = []

        if flow_id:
            flow_config = await self.storage.get_flow_config(flow_id)
            if not flow_config:
                raise ValueError(f"Flow {flow_id} not found")

            platform_config = flow_config.platforms.get(platform)
            if not platform_config:
                raise ValueError(f"Flow {flow_id} does not have platform {platform}")

            if platform_config.get("username") == username:
                flows_to_register.append((flow_id, platform_config))
        else:
            all_keys = await self.storage.list_by_prefix("", 1000, force_global=True)
            flow_keys = [key for key in all_keys if ":flow:" in key]

            for flow_key in flow_keys:
                flow_data = await self.storage.get(flow_key, force_global=True)
                if not flow_data:
                    continue

                flow_config = FlowConfig.model_validate_json(flow_data)
                platform_config = flow_config.platforms.get(platform)

                if platform_config and platform_config.get("username") == username:
                    flows_to_register.append((flow_config.flow_id, platform_config))

        if not flows_to_register:
            raise ValueError(f"No flows found for {platform}:{username}")

        # Регистрируем каждый flow
        results = []
        for fid, pconfig in flows_to_register:
            result = await interface_class.register(fid, username, pconfig)
            results.append({
                "flow_id": fid,
                "result": result
            })
            logger.info(f"✅ {platform} зарегистрирован для {fid}: {result}")

        return {
            "success": True,
            "platform": platform,
            "username": username,
            "flows_registered": len(results),
            "details": results
        }
