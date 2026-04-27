"""
Конфигурация сервиса browser (Browser Runtime).
"""

from __future__ import annotations

from typing import Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from apps.browser.engine.types import BrowserRuntimeSettingsView
from core.config import BaseSettings
from core.config.loader import load_merged_config


class BrowserRuntimeIntegrationConfig(BaseModel):
    """
    Конфигурация Browser Runtime, из которой собирается рабочий фасад сервиса.

    Мотивация:
    - Держать все runtime-переключатели в одном месте и валидировать их на старте.
    - Разделить transport-настройки, lifecycle параметры и выбор backend-а.

    Связи:
    - Читается `BrowserSettings` и преобразуется в `BrowserRuntimeSettingsView`.
    - Определяет CDP endpoint-ы и backend адаптера control API.

    Состояние:
    - Набор pydantic-полей с валидацией диапазонов и допустимых значений.

    Инварианты:
    - Неизвестные поля запрещены (`extra="forbid"`).
    - `default_page_ttl_sec` и `warm_idle_sec` валидируются на неотрицательные границы.
    - `control_backend` ограничен перечислением поддержанных реализаций.

    Переиспользование:
    - Стоит: для всех окружений (dev/test/prod), где нужен единый контракт настроек.
    """
    model_config = ConfigDict(extra="forbid")

    default_endpoint_key: str = Field(default="default")
    cdp_url: str = Field(default="")
    cdp_endpoints: dict[str, str] = Field(default_factory=dict)
    artifacts_dir: str = Field(default="artifacts/browser_runtime")
    default_page_ttl_sec: int = Field(default=3600, ge=60)
    warm_idle_sec: int = Field(default=300, ge=0)
    init_scripts_version: str = Field(default="v1")
    control_backend: Literal["playwright", "browser_use", "agent_browser"] = Field(
        default="playwright",
    )
    e2e_lightpanda: bool = Field(default=False)
    e2e_lightpanda_cdp_url: str = Field(default="")


class BrowserSettings(BaseSettings):
    """
    Корневой settings-объект сервиса browser.

    Связи:
    - Создаётся в `get_browser_settings` через общий загрузчик конфигурации.
    - Передаётся в DI-контейнер и далее преобразуется в runtime view.

    Состояние:
    - Содержит секцию `browser` с runtime-параметрами.

    Инварианты:
    - `browser` всегда присутствует (даже при дефолтной инициализации).

    Мотивация:
    - Подключить browser runtime к общей платформенной схеме загрузки настроек.

    Переиспользование:
    - Стоит: как единый settings-класс сервиса browser.
    """
    browser: BrowserRuntimeIntegrationConfig = Field(
        default_factory=BrowserRuntimeIntegrationConfig,
    )


@runtime_checkable
class HasBrowserRuntimeConfig(Protocol):
    """
    Минимальный типовой контракт для функций, которым нужен доступ к `settings.browser`.

    Связи:
    - Используется `settings_to_runtime_view` для типобезопасного доступа к полям runtime.

    Инварианты:
    - Реализация обязана иметь атрибут `browser` типа `BrowserRuntimeIntegrationConfig`.

    Мотивация:
    - Ослабить типовую связанность helper-функций с конкретным классом settings.

    Переиспользование:
    - Стоит: в helper-функциях, которым важен только доступ к `browser`.
    """
    browser: BrowserRuntimeIntegrationConfig


_browser_settings: Optional[BrowserSettings] = None


def get_browser_settings() -> BrowserSettings:
    global _browser_settings
    if _browser_settings is None:
        merged = load_merged_config(service_name="browser")
        _browser_settings = BrowserSettings(**merged)
    return _browser_settings


def reset_browser_settings() -> None:
    global _browser_settings
    _browser_settings = None


def settings_to_runtime_view(settings: HasBrowserRuntimeConfig) -> BrowserRuntimeSettingsView:
    cfg = settings.browser
    endpoints = dict(cfg.cdp_endpoints)
    if cfg.cdp_url:
        endpoints[cfg.default_endpoint_key] = cfg.cdp_url
    if len(endpoints) == 0:
        raise ValueError(
            "Не задан CDP endpoint: укажите browser.cdp_url или browser.cdp_endpoints "
            "(например ENV BROWSER__CDP_URL)."
        )
    if cfg.default_endpoint_key not in endpoints:
        raise ValueError(
            f"default_endpoint_key={cfg.default_endpoint_key!r} отсутствует в browser.cdp_endpoints"
        )
    empty_keys = sorted(key for key, value in endpoints.items() if not value)
    if len(empty_keys) > 0:
        joined = ", ".join(empty_keys)
        raise ValueError(f"Пустой CDP URL для endpoint(s): {joined}")
    return BrowserRuntimeSettingsView(
        default_endpoint_key=cfg.default_endpoint_key,
        cdp_urls_by_endpoint=endpoints,
        artifacts_dir=cfg.artifacts_dir,
        default_page_ttl_sec=cfg.default_page_ttl_sec,
        warm_idle_sec=cfg.warm_idle_sec,
        init_scripts_version=cfg.init_scripts_version,
        control_backend=cfg.control_backend,
    )
