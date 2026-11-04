"""Конфигурация Shop Service.

URL БД — `database.shop_url`, адреса соседей — `server.*_service_url`.
Публичные поверхности витрин задаются здесь: суффикс wildcard-доменов
платформы и хост агрегатора.
"""

from pydantic import Field

from core.config import BaseSettings


class ShopSettings(BaseSettings):
    """Настройки сервиса витрин и агрегатора."""

    storefront_domain_suffix: str = Field(
        default="linnex.io",
        description="Домен-суффикс slug-витрин: <slug>.<suffix>. Пустой — slug-витрины отключены, остаются кастомные домены.",
    )
    aggregator_host: str = Field(
        default="shop.linnex.io",
        description="Хост публичного агрегатора поиска по всем витринам.",
    )
    reserved_slugs: frozenset[str] = Field(
        default=frozenset(
            {
                "www",
                "api",
                "app",
                "mail",
                "smtp",
                "grafana",
                "livekit",
                "onlyoffice",
                "shop",
                "admin",
                "support",
                "status",
                "docs",
                "cdn",
                "static",
            }
        ),
        description="Поддомены, недоступные для slug витрин: инфраструктура и служебные.",
    )
    storefront_snapshot_ttl_seconds: int = Field(
        default=86400,
        description="TTL Redis-снапшота витрины; инвалидация — событием, TTL — страховка.",
    )
    storefront_negative_ttl_seconds: int = Field(
        default=30,
        description="TTL негативного кэша «витрины нет» — защита от stampede по свободным slug'ам.",
    )
    taskiq_wait_timeout: float = Field(
        default=30.0,
        description="Таймаут ожидания результата taskiq (provisioning домена и т.п.).",
    )
    ai_a2a_timeout_seconds: float = Field(
        default=90.0,
        ge=15.0,
        le=600.0,
        description="Бюджет ожидания A2A при вызове веток системного flow ``shop`` (describe/suggest_options), сек.",
    )
    order_rate_limit_per_minute: int = Field(
        default=10,
        description="Заказов в минуту с одного IP на витрину (Redis-счётчик).",
    )
    similar_name_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Порог pg_trgm similarity названия: новое блюдо с похожим именем получает similar_shop_product_id.",
    )
    telegram_bot_token: str = Field(
        default="",
        description="Токен платформенного Telegram-бота shop для уведомлений владельцам; секрет через env/conf.local.",
    )
