"""
Конфигурация сервиса office (Documents / OnlyOffice).
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from core.config import BaseSettings
from core.config import set_settings as core_set_settings
from core.config.loader import load_merged_config
from core.config.models import ServerConfig


class OfficeEditorCustomizationSettings(BaseModel):
    """editorConfig.customization (standard branding OnlyOffice CE)."""

    compact_toolbar: bool = True
    compact_header: bool = True
    ui_theme: str = Field(
        default="theme-platform-docs-light",
        description=(
            "Встроенная тема (theme-light, …) или id JSON-темы на Document Server "
            "(theme-platform-docs-light)"
        ),
    )
    features_tips: bool = Field(
        default=False,
        description="Подсказки о новых возможностях при первом открытии редактора",
    )
    tab_style: Literal["line", "fill"] = Field(
        default="line",
        description="Стиль вкладок toolbar: line (underline) или fill",
    )
    tab_background: Literal["toolbar", "header"] = Field(
        default="toolbar",
        description="Фон вкладок: toolbar (белый) или header",
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

    server: ServerConfig = Field(default_factory=ServerConfig)
    office: OfficeIntegrationConfig = Field(default_factory=OfficeIntegrationConfig)

    @model_validator(mode="after")
    def _default_office_server_identity(self) -> "OfficeSettings":
        if self.server.name == "core":
            self.server = self.server.model_copy(update={"name": "documents", "port": 8008})
        return self


_office_settings: OfficeSettings | None = None


def get_office_settings() -> OfficeSettings:
    global _office_settings
    if _office_settings is None:
        merged = load_merged_config(service_name="office", silent=True)
        _office_settings = OfficeSettings.model_validate(merged)
        core_set_settings(_office_settings)
    return _office_settings


def reset_office_settings() -> None:
    global _office_settings
    _office_settings = None
