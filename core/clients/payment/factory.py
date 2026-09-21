"""
Фабрика для создания платежных провайдеров.
"""

from typing import TypeAlias

from core.clients.payment.tinkoff_provider import TinkoffConfig, TinkoffProvider
from core.config import get_settings
from core.config.models import PaymentProviderConfigEntry
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

PaymentProvider: TypeAlias = TinkoffProvider


class PaymentProviderFactory:
    """Фабрика для управления платежными провайдерами"""

    _providers: dict[str, PaymentProvider] = {}
    _configs: dict[str, PaymentProviderConfigEntry] = {}

    @classmethod
    def initialize(cls) -> None:
        settings = get_settings()

        logger.info("payments.providers_initialize")

        if not settings.payment_providers.providers:
            logger.warning("payments.providers_missing_in_config")
            return

        cls._providers = {}
        cls._configs = {}
        for provider_name, provider_config in settings.payment_providers.providers.items():
            cls._configs[provider_name] = provider_config

            config_obj = cls._create_config_object(provider_config)

            if not config_obj.enabled:
                logger.info("payments.provider_disabled", provider=provider_name)
                continue

            provider = cls._create_provider(config_obj)
            provider.registry_name = provider_name
            cls._providers[provider_name] = provider

            logger.info(
                "payments.provider_initialized",
                provider=provider_name,
                provider_type=config_obj.provider_type,
            )

        if cls._providers:
            logger.info(
                "payments.providers_ready",
                count=len(cls._providers),
                names=",".join(cls._providers.keys()),
            )
        else:
            logger.warning("payments.providers_none_enabled")

    @classmethod
    def _create_config_object(cls, config_entry: PaymentProviderConfigEntry) -> TinkoffConfig:
        terminal_key = config_entry.terminal_key.strip()
        password = config_entry.password.strip()
        api_url = config_entry.api_url.strip()
        if terminal_key == "":
            raise ValueError("terminal_key is required for Tinkoff")
        if password == "":
            raise ValueError("password is required for Tinkoff")
        if api_url == "":
            raise ValueError("api_url is required for Tinkoff")
        return TinkoffConfig(
            provider_type="tinkoff",
            enabled=config_entry.enabled,
            terminal_key=terminal_key,
            password=password,
            api_url=api_url,
            receipt_enabled=config_entry.receipt_enabled,
            taxation=config_entry.taxation,
        )

    @classmethod
    def _create_provider(cls, config: TinkoffConfig) -> PaymentProvider:
        return TinkoffProvider(config)

    @classmethod
    def get_provider(cls, provider_name: str) -> PaymentProvider | None:
        provider = cls._providers.get(provider_name)
        if not provider:
            logger.warning("payments.provider_not_found", provider=provider_name)
        return provider

    @classmethod
    def get_available_providers(cls) -> dict[str, PaymentProvider]:
        return cls._providers.copy()

    @classmethod
    def get_default_provider(cls) -> PaymentProvider | None:
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
        return [
            {
                "name": name,
                "type": provider.config.provider_type,
                "enabled": provider.is_enabled(),
            }
            for name, provider in cls._providers.items()
        ]
