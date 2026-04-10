"""
Фабрика для создания платежных провайдеров.
Единая точка создания провайдеров из конфигурации.

АДАПТИРОВАНО: убраны try-except блоки
"""

import logging
from typing import Dict, Optional

from core.config import get_settings
from core.clients.payment.base_provider import BasePaymentProvider
from core.clients.payment.yoomoney_provider import YooMoneyProvider, YooMoneyConfig
from core.clients.payment.yukassa_provider import YuKassaProvider, YuKassaConfig

logger = logging.getLogger(__name__)


class PaymentProviderFactory:
    """Фабрика для управления платежными провайдерами"""
    
    _providers: Dict[str, BasePaymentProvider] = {}
    _configs: Dict[str, any] = {}
    
    @classmethod
    def initialize(cls):
        """
        Инициализация всех провайдеров из конфигурации.
        Вызывается при старте приложения.
        """
        settings = get_settings()
        
        logger.info("Инициализация платежных провайдеров...")
        
        if not settings.payment_providers.providers:
            logger.warning("В конфигурации нет платежных провайдеров")
            return
        
        for provider_name, provider_config in settings.payment_providers.providers.items():
            cls._configs[provider_name] = provider_config
            
            config_obj = cls._create_config_object(provider_config)
            
            if not config_obj.enabled:
                logger.info(f"Платежный провайдер {provider_name} отключен")
                continue
            
            provider = cls._create_provider(provider_name, config_obj)
            cls._providers[provider_name] = provider
            
            logger.info(
                f"Платежный провайдер {provider_name} ({config_obj.provider_type}) инициализирован"
            )
        
        if cls._providers:
            logger.info(f"Инициализировано провайдеров: {len(cls._providers)} ({', '.join(cls._providers.keys())})")
        else:
            logger.warning("Не инициализировано ни одного платежного провайдера")
    
    @classmethod
    def _create_config_object(cls, config_dict):
        """Создает объект конфигурации из словаря или Pydantic-модели"""
        if hasattr(config_dict, "model_dump"):
            config_dict = config_dict.model_dump(exclude_none=False)

        provider_type = config_dict.get("provider_type")

        if not provider_type:
            raise ValueError("provider_type не указан в конфигурации")

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
    def get_default_provider(cls) -> Optional[BasePaymentProvider]:
        """Возвращает дефолтный провайдер"""
        settings = get_settings()
        
        if settings.payment_providers.default_provider:
            default = settings.payment_providers.default_provider
            if default in cls._providers:
                return cls._providers[default]
        
        if cls._providers:
            return next(iter(cls._providers.values()))
        
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
    
    @classmethod
    def get_provider_for_company(cls, company) -> Optional[BasePaymentProvider]:
        """
        Получает провайдер для компании.
        
        Если у компании указан payment_provider - возвращает его.
        Иначе возвращает дефолтный провайдер.
        
        Args:
            company: Объект Company с атрибутом payment_provider (опционально)
            
        Returns:
            Провайдер для компании или None если провайдеров нет
        """
        if not cls._providers:
            return None
        
        if hasattr(company, 'payment_provider') and company.payment_provider:
            provider = cls.get_provider(company.payment_provider)
            if provider:
                return provider
        
        return cls.get_default_provider()

