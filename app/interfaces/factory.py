import json
import logging
from typing import Optional, Dict, Any

from app.interfaces.base import BaseInterface
from app.interfaces.telegram_interface import TelegramInterface
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
        interface_class = self.PLATFORM_INTERFACES.get(platform)
        if not interface_class:
            raise ValueError(f"Неизвестная платформа: {platform}")
        
        if platform == "api":
            return None
        
        if platform == "telegram":
            bot_username = config.get("bot_username")
            if not bot_username:
                logger.error("Нет bot_username для создания Telegram интерфейса")
                return None

            token_key = f"token:telegram:{bot_username}"
            token_json = await self.storage.get(token_key, force_global=True)

            if not token_json:
                logger.error(f"Не найден токен для бота {bot_username}")
                return None

            bot_token = json.loads(token_json)
            return TelegramInterface(bot_token, {"username": bot_username})
        
        return interface_class(config)

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

