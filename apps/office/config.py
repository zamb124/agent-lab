"""
Конфигурация сервиса office (Documents / OnlyOffice).
"""

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from core.config import BaseSettings
from core.config.loader import load_merged_config


class OfficeEditorCustomizationSettings(BaseModel):
    """editorConfig.customization (standard branding OnlyOffice)."""

    compact_toolbar: bool = True
    compact_header: bool = True
    ui_theme: str = Field(
        default="theme-light",
        description="Встроенная тема (theme-light, theme-classic-light, …) или id JSON-темы на Document Server (theme-*)",
    )
    logo_image_url: str = Field(
        default="",
        description="Абсолютный URL логотипа; должен быть доступен с origin Document Server",
    )
    logo_image_dark_url: str = Field(default="")
    logo_link_url: str = Field(default="")
    platform_header_branding: bool = Field(
        default=True,
        description=(
            "Если true и logo_image_url пуст — в шапке редактора логотип и ссылка Humanitec "
            "(статика /static/core/.../frontend_logo.svg на BFF office; base URL см. branding_public_base_url)"
        ),
    )
    branding_public_base_url: str = Field(
        default="",
        description=(
            "Origin для URL логотипа в JWT (без слэша в конце). Пусто — office_service_url, "
            "иначе platform_public_base_url, иначе frontend_service_url"
        ),
    )
    features_tips: bool = Field(
        default=False,
        description="Подсказки о новых возможностях при первом открытии редактора",
    )


class OfficeIntegrationConfig(BaseModel):
    """Параметры OnlyOffice Document Server и публичных URL для DS."""

    document_server_public_url: str = Field(
        default="",
        description=(
            "Origin для api.js и статики DS в браузере — тот же публичный host, что страница /documents "
            "(ingress или dev middleware + document_server_dev_upstream_url)."
        ),
    )
    jwt_secret: str = Field(
        default="",
        description="Тот же секрет, что JWT_SECRET в контейнере onlyoffice/documentserver",
    )
    callback_public_base_url: str = Field(
        default="",
        description=(
            "Публичный базовый URL BFF, доступный с Document Server: скачивание файла и callback "
            "(например http://host.docker.internal:8008 или https://app.example.com)"
        ),
    )
    download_token_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    editor_customization: OfficeEditorCustomizationSettings = Field(
        default_factory=OfficeEditorCustomizationSettings,
    )


class OfficeSettings(BaseSettings):
    """Настройки сервиса office."""

    office: OfficeIntegrationConfig = Field(default_factory=OfficeIntegrationConfig)

    @model_validator(mode="after")
    def _default_office_server_identity(self) -> "OfficeSettings":
        if self.server.name == "core":
            self.server = self.server.model_copy(update={"name": "documents", "port": 8008})
        return self


_office_settings: Optional[OfficeSettings] = None


def get_office_settings() -> OfficeSettings:
    global _office_settings
    if _office_settings is None:
        from core.config import set_settings as core_set_settings

        merged = load_merged_config(service_name="office")
        server_block = dict(merged.get("server") or {})
        server_block.setdefault("name", "documents")
        server_block.setdefault("port", 8008)
        merged["server"] = server_block
        _office_settings = OfficeSettings(**merged)
        core_set_settings(_office_settings)
    return _office_settings


def reset_office_settings() -> None:
    global _office_settings
    _office_settings = None
