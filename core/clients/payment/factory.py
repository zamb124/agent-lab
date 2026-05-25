"""
Фабрика для создания платежных провайдеров.
Единая точка создания провайдеров из конфигурации.

АДАПТИРОВАНО: убраны try-except блоки
"""

from typing import TypeAlias

from core.clients.payment.yoomoney_provider import (
    YOOMONEY_API_URL,
    YooMoneyConfig,
    YooMoneyProvider,
    load_access_token,
    save_access_token,
)
from core.clients.payment.yukassa_provider import YUKASSA_API_URL, YuKassaConfig, YuKassaProvider
from core.config import get_settings
from core.config.models import PaymentProviderConfigEntry
from core.db.storage import Storage
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

PaymentProvider: TypeAlias = YooMoneyProvider | YuKassaProvider


class PaymentProviderFactory:
    """Фабрика для управления платежными провайдерами"""

    _providers: dict[str, PaymentProvider] = {}
    _configs: dict[str, PaymentProviderConfigEntry] = {}

    @classmethod
    def initialize(cls) -> None:
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

            provider = cls._create_provider(config_obj)
            cls._providers[provider_name] = provider

            logger.info(
                f"Платежный провайдер {provider_name} ({config_obj.provider_type}) инициализирован"
            )

        if cls._providers:
            logger.info(f"Инициализировано провайдеров: {len(cls._providers)} ({', '.join(cls._providers.keys())})")
        else:
            logger.warning("Не инициализировано ни одного платежного провайдера")

    @classmethod
    def _create_config_object(cls, config_entry: PaymentProviderConfigEntry) -> YooMoneyConfig | YuKassaConfig:
        """Создает объект конфигурации из словаря или Pydantic-модели"""
        if config_entry.provider_type == "yoomoney":
            account_number = config_entry.account_number
            notification_secret = config_entry.notification_secret
            quickpay_url = config_entry.quickpay_url
            api_url = config_entry.api_url if config_entry.api_url is not None else YOOMONEY_API_URL
            if account_number is None or account_number.strip() == "":
                raise ValueError("account_number обязателен для YooMoney")
            if notification_secret is None or notification_secret.strip() == "":
                raise ValueError("notification_secret обязателен для YooMoney")
            if quickpay_url.strip() == "":
                raise ValueError("quickpay_url обязателен для YooMoney")
            if api_url.strip() == "":
                raise ValueError("api_url обязателен для YooMoney")
            return YooMoneyConfig(
                provider_type="yoomoney",
                enabled=config_entry.enabled,
                account_number=account_number,
                notification_secret=notification_secret,
                quickpay_url=quickpay_url,
                client_id=config_entry.client_id,
                client_secret=config_entry.client_secret,
                access_token=config_entry.access_token,
                api_url=api_url,
            )

        shop_id = config_entry.shop_id
        secret_key = config_entry.secret_key
        api_url = config_entry.api_url if config_entry.api_url is not None else YUKASSA_API_URL
        if shop_id is None or shop_id.strip() == "":
            raise ValueError("shop_id обязателен для ЮKassa")
        if secret_key is None or secret_key.strip() == "":
            raise ValueError("secret_key обязателен для ЮKassa")
        if api_url.strip() == "":
            raise ValueError("api_url обязателен для ЮKassa")
        return YuKassaConfig(
            provider_type="yukassa",
            enabled=config_entry.enabled,
            shop_id=shop_id,
            secret_key=secret_key,
            api_url=api_url,
        )

    @classmethod
    def _create_provider(
        cls, config: YooMoneyConfig | YuKassaConfig
    ) -> PaymentProvider:
        """Создает экземпляр провайдера по типу"""

        if isinstance(config, YooMoneyConfig):
            return YooMoneyProvider(config)
        return YuKassaProvider(config)

    @classmethod
    def get_provider(cls, provider_name: str) -> PaymentProvider | None:
        """Получает провайдер по имени"""
        provider = cls._providers.get(provider_name)
        if not provider:
            logger.warning(f"Провайдер {provider_name} не найден")
        return provider

    @classmethod
    def get_available_providers(cls) -> dict[str, PaymentProvider]:
        """Возвращает все доступные провайдеры"""
        return cls._providers.copy()

    @classmethod
    def get_default_provider(cls) -> PaymentProvider | None:
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
    def list_providers(cls) -> list[JsonObject]:
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
    async def seed_access_tokens(cls, storage: Storage) -> None:
        """Загружает access_token из конфига в storage, если в storage пусто."""
        for provider in cls._providers.values():
            if not isinstance(provider, YooMoneyProvider):
                continue
            if not provider.config.access_token:
                continue
            existing = await load_access_token(storage)
            if existing:
                logger.info("YooMoney access_token уже есть в storage (истекает %s)", existing.expires_at)
                provider.set_access_token(existing.token)
                continue
            token_data = await save_access_token(storage, provider.config.access_token)
            provider.set_access_token(provider.config.access_token)
            logger.info("YooMoney access_token загружен из конфига в storage (истекает %s)", token_data.expires_at)
