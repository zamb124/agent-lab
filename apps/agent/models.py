"""
Модели данных для HumanitecAgent.
"""

from datetime import datetime, timezone
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

AgentPlatform = Literal["windows", "macos-arm64", "macos-x64", "linux-deb", "linux-rpm", "linux-appimage"]


class DevicePolicy(BaseModel):
    """Политика безопасности для устройства HumanitecAgent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    allowed_roots: list[str] = Field(
        default_factory=list,
        description="Разрешённые корневые папки для filesystem MCP",
    )
    exec_whitelist: list[str] = Field(
        default_factory=list,
        description="Разрешённые команды для shell MCP (пусто = deny all)",
    )
    exec_require_confirm: bool = Field(
        default=True,
        description="Требовать подтверждение пользователя перед каждым exec",
    )
    shell_enabled: bool = Field(
        default=False,
        description="Shell MCP включён (по умолчанию выключен)",
    )
    browser_enabled: bool = Field(
        default=True,
        description="Playwright MCP включён",
    )
    max_file_size_mb: int = Field(
        default=50,
        ge=1,
        description="Максимальный размер файла для чтения MCP, МБ",
    )
    audit_retention_days: int = Field(
        default=30,
        ge=1,
        description="Срок хранения audit-логов MCP вызовов, дней",
    )


class AgentDeviceRecord(BaseModel):
    """Зарегистрированное устройство HumanitecAgent в БД."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    device_id: str = Field(description="UUID устройства")
    device_name: str = Field(description="Имя устройства")
    user_id: str = Field(description="ID пользователя")
    company_id: str = Field(description="ID компании")
    os: str = Field(description="ОС: darwin/linux/win32")
    hostname: str = Field(description="hostname машины")
    paired_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Дата pairing",
    )
    last_seen_at: datetime | None = Field(
        default=None,
        description="Последняя активность",
    )
    policy: DevicePolicy = Field(default_factory=DevicePolicy)
    is_active: bool = Field(default=True, description="Активно ли устройство")
    active_device_jti: str | None = Field(
        default=None,
        description="jti последнего выпущенного device JWT",
    )


class DeviceRegisterRequest(BaseModel):
    """Запрос на регистрацию устройства от HumanitecAgent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    pairing_code: str = Field(
        min_length=6,
        max_length=6,
        description="6-значный pairing code из браузера",
    )
    device_id: str = Field(min_length=1, description="UUID устройства")
    device_name: str = Field(min_length=1, description="Имя устройства")
    os: str = Field(min_length=1, description="ОС")
    hostname: str = Field(min_length=1, description="hostname")


class AgentLlmBundle(BaseModel):
    """OpenAI-compatible LLM endpoint для HumanitecAgent после pairing."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider_id: Literal["humanitec"] = "humanitec"
    model_id: Literal["auto"] = "auto"
    api_base_url: str = Field(description="Base URL без /chat/completions (Goose добавляет path)")


class DeviceRegisterResponse(BaseModel):
    """Ответ при успешной регистрации устройства."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    device_id: str
    token: str = Field(description="Device JWT (30 дней)")
    platform_mcp_url: str = Field(description="URL Platform MCP endpoint для Goose")
    frontend_base_url: str = Field(description="Публичный origin frontend для API и deep links")
    tunnel_ws_url: str = Field(description="WebSocket URL tunnel HumanitecAgent")
    company_id: str = Field(description="ID компании, привязанной при pairing")
    company_subdomain: str | None = Field(
        default=None,
        description="Subdomain компании для UI и документации",
    )
    llm: AgentLlmBundle = Field(description="Platform LLM bundle для Goose openai-compatible provider")


class DeviceRegisterWithAuthRequest(BaseModel):
    """Регистрация устройства по browser session JWT (без pairing code)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, description="UUID устройства")
    device_name: str = Field(min_length=1, description="Имя устройства")
    os: str = Field(min_length=1, description="ОС")
    hostname: str = Field(min_length=1, description="hostname")


class PairingCodeResponse(BaseModel):
    """Ответ при создании pairing code в браузере."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    pairing_code: str = Field(min_length=6, max_length=6)
    expires_in_seconds: int = Field(ge=60)


class AgentDeviceListItem(BaseModel):
    """Устройство в списке для UI/API."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    device_id: str
    device_name: str
    user_id: str
    company_id: str
    os: str
    hostname: str
    paired_at: datetime
    last_seen_at: datetime | None = None
    is_active: bool = True
    is_tunnel_online: bool = Field(default=False, description="Tunnel WS активен")
    policy: DevicePolicy = Field(default_factory=DevicePolicy)


class AgentReleaseAssetChecksum(BaseModel):
    """Checksum арtefact release для integrity check."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    asset_name: str
    sha256: str


class AgentReleaseStatusResponse(BaseModel):
    """Статус GitHub release для лендинга и диагностики."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    ready: bool
    latest_tag: str | None = None
    github_owner: str
    github_repo: str
    detail: str | None = None
    asset_checksums: list[AgentReleaseAssetChecksum] = Field(default_factory=list)


class AgentDiscoverResponse(BaseModel):
    """Публичный discover HumanitecAgent до pairing."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    frontend_base_url: str
    platform_mcp_url: str
    tunnel_ws_url: str
    llm_api_url: str
    releases: AgentReleaseStatusResponse


class AgentDeviceListResponse(BaseModel):
    """Список устройств компании."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[AgentDeviceListItem] = Field(default_factory=list)


class DevicePolicyUpdateRequest(BaseModel):
    """Обновление политики устройства HumanitecAgent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    policy: DevicePolicy


class AgentAuditEvent(BaseModel):
    """Запись audit-лога HumanitecAgent."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    event_type: str
    actor_user_id: str | None = None
    device_id: str | None = None
    detail: str
    recorded_at: datetime


class AgentAuditListResponse(BaseModel):
    """Список audit-событий компании."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[AgentAuditEvent] = Field(default_factory=list)


class AgentLoginResponse(BaseModel):
    """Контекст для страницы логина HumanitecAgent."""

    redirect_uri: str = Field(default="humanitec://auth/callback")
    already_logged_in: bool = Field(default=False)
    user_email: str | None = Field(default=None)


class DeviceTokenClaims(BaseModel):
    """Claims для device JWT."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    user_id: str
    company_id: str
    device_id: str
    iat: int
    exp: int
    token_type: str = "device"
