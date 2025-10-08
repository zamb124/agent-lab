"""
Фабрика для создания платежных провайдеров.
Аналогично LLM Factory - единая точка создания провайдеров.
"""

import logging
from typing import Dict, Optional

from .base_provider import BasePaymentProvider
from .yoomoney_provider import YooMoneyProvider, YooMoneyConfig
from .yukassa_provider import YuKassaProvider, YuKassaConfig

logger = logging.getLogger(__name__)


class PaymentProviderFactory:
    """Фабрика для управления платежными провайдерами"""
    
    _providers: Dict[str, BasePaymentProvider] = {}
    _configs: Dict[str, any] = {}
    
    @classmethod
    def initialize(cls, settings):
        """
        Инициализация всех провайдеров из конфигурации.
        Вызывается при старте приложения.
        """
        
        logger.info("Инициализация платежных провайдеров...")
        
        if not hasattr(settings, 'payment_providers') or not settings.payment_providers.providers:
            logger.warning("В конфигурации нет платежных провайдеров")
            return
        
        for provider_name, provider_config in settings.payment_providers.providers.items():
            try:
                cls._configs[provider_name] = provider_config
                
                # provider_config это словарь из JSON, преобразуем в объект
                config_obj = cls._create_config_object(provider_config)
                
                if not config_obj.enabled:
                    logger.info(f"⚠️ Платежный провайдер {provider_name} отключен")
                    continue
                
                provider = cls._create_provider(provider_name, config_obj)
                cls._providers[provider_name] = provider
                
                logger.info(
                    f"✅ Платежный провайдер {provider_name} "
                    f"({config_obj.provider_type}) инициализирован"
                )
                
            except Exception as e:
                logger.error(
                    f"❌ Ошибка инициализации провайдера {provider_name}: {e}",
                    exc_info=True
                )
        
        if cls._providers:
            logger.info(
                f"Инициализировано провайдеров: {len(cls._providers)} "
                f"({', '.join(cls._providers.keys())})"
            )
        else:
            logger.warning("Не инициализировано ни одного платежного провайдера")
    
    @classmethod
    def _create_config_object(cls, config_dict: dict):
        """Создает объект конфигурации из словаря"""
        provider_type = config_dict.get("provider_type")
        
        if provider_type == "yoomoney":
            return YooMoneyConfig(**config_dict)
        elif provider_type == "yukassa":
            return YuKassaConfig(**config_dict)
        else:
            raise ValueError(f"Неизвестный тип провайдера: {provider_type}")
    
    @classmethod
    def _create_provider(cls, provider_name: str, config) -> BasePaymentProvider:
        """Создает экземпляр провайдера по типу"""
        
        provider_type = config.provider_type
        
        if provider_type == "yoomoney":
            return YooMoneyProvider(config)
        elif provider_type == "yukassa":
            return YuKassaProvider(config)
        else:
            raise ValueError(f"Неизвестный тип провайдера: {provider_type}")
    
    @classmethod
    def get_provider(cls, provider_name: str) -> Optional[BasePaymentProvider]:
        """Получает провайдер по имени"""
        provider = cls._providers.get(provider_name)
        if not provider:
            logger.warning(f"Провайдер {provider_name} не найден")
        return provider
    
    @classmethod
    def get_available_providers(cls) -> Dict[str, BasePaymentProvider]:
        """Возвращает все доступные провайдеры"""
        return cls._providers.copy()
    
    @classmethod
    def get_provider_for_company(cls, company) -> Optional[BasePaymentProvider]:
        """
        Получает провайдер для конкретной компании.
        Использует company.payment_provider если указан, иначе дефолтный.
        """
        
        provider_name = getattr(company, 'payment_provider', None)
        
        if provider_name:
            provider = cls.get_provider(provider_name)
            if provider:
                return provider
            logger.warning(
                f"Указанный провайдер {provider_name} для компании "
                f"{company.company_id} не найден, используем дефолтный"
            )
        
        default_provider = cls._get_default_provider()
        if default_provider:
            return cls.get_provider(default_provider)
        
        logger.error("Нет доступных платежных провайдеров")
        return None
    
    @classmethod
    def _get_default_provider(cls) -> Optional[str]:
        """Возвращает дефолтный провайдер из конфига или первый доступный"""
        from ...config import settings
        
        if hasattr(settings, 'payment_providers') and settings.payment_providers.default_provider:
            default = settings.payment_providers.default_provider
            if default in cls._providers:
                return default
        
        if cls._providers:
            return next(iter(cls._providers.keys()))
        return None
    
    @classmethod
    def list_providers(cls) -> list:
        """Возвращает список доступных провайдеров с метаданными"""
        return [
            {
                "name": name,
                "type": provider.config.provider_type,
                "enabled": provider.is_enabled()
            }
            for name, provider in cls._providers.items()
        ]
