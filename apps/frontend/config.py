"""
Конфигурация для Frontend Service.

Расширяет BaseSettings добавляя специфичные для Frontend поля.
"""


from pydantic import Field

from core.config import BaseSettings
from core.config.service_settings import ServiceSettingsCache


class FrontendSettings(BaseSettings):
    """
    Настройки Frontend сервиса.

    Наследуется от BaseSettings, добавляя специфичные для Frontend поля.
    Все базовые поля (database, auth, logging, etc) доступны из родителя.
    """

    cors_allow_origins: list[str] = Field(default_factory=list)
    cors_allow_origin_regex: str | None = None
    indexnow_key: str | None = Field(
        default=None,
        description=(
            "IndexNow ключ верификации: frontend отдаёт /<key>.txt, "
            "scripts.seo.index_now шлёт URL в Bing/Yandex после выката."
        ),
    )


_settings_cache = ServiceSettingsCache("frontend", FrontendSettings)
get_frontend_settings = _settings_cache.get
reset_frontend_settings = _settings_cache.reset
