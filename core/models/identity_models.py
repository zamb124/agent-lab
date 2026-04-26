"""
Модели для системы идентификации и авторизации.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, ConfigDict, model_validator
from enum import Enum

from core.fields import Field
from core.models.billing_models import TariffPlan


class UserStatus(str, Enum):
    """Статус пользователя"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"


class AuthProvider(str, Enum):
    """Перечисление доступных провайдеров авторизации"""

    YANDEX = "yandex"
    GOOGLE = "google"
    GITHUB = "github"
    APPLE = "apple"
    DEMO = "demo"


class User(BaseModel):
    """
    Основная модель пользователя (хранится в user:user_id).
    Содержит только общие данные, без привязки к провайдерам.
    """

    model_config = ConfigDict(
        json_schema_extra={"storage_prefix": "user"}
    )

    user_id: str = Field(
        title="ID пользователя",
        description="Уникальный ID пользователя в системе",
        readonly=True,
    )
    name: str = Field(
        title="Имя",
        description="Отображаемое имя; при сохранении ФИО может выставляться из имени и фамилии",
        placeholder="Иван Иванов",
        max_length=200,
    )
    first_name: Optional[str] = Field(
        default=None,
        title="Имя",
        description="Имя для профиля и сопоставления на графе",
        max_length=100,
    )
    last_name: Optional[str] = Field(
        default=None,
        title="Фамилия",
        description="Фамилия для профиля и сопоставления на графе",
        max_length=100,
    )
    status: UserStatus = Field(
        default=UserStatus.ACTIVE,
        title="Статус",
        description="Статус пользователя",
        groups={"admin": {"editable_in_table": True}, "user": {"readonly": True}},
    )
    groups: List[str] = Field(
        default=["user"],
        title="Группы",
        description="Группы пользователя (admin, user, bot_editor, guest)",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    companies: Dict[str, List[str]] = Field(
        default_factory=dict,
        title="Компании и роли",
        description="company_id -> [role1, role2]",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    active_company_id: str = Field(
        default="",
        title="Активная компания",
        description="ID текущей активной компании",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    emails: List[str] = Field(
        default_factory=list,
        title="Email адреса",
        description="Список email адресов пользователя"
    )
    phones: List[str] = Field(
        default_factory=list,
        title="Телефоны",
        description="Список телефонных номеров"
    )
    messengers: Dict[str, str] = Field(
        default_factory=dict,
        title="Мессенджеры",
        description="Контакты в мессенджерах: {telegram: @username, whatsapp: +123, slack: U12345}"
    )
    avatar_url: Optional[str] = Field(
        default=None,
        title="Аватар",
        description="URL аватара пользователя"
    )
    bio: Optional[str] = Field(
        default=None,
        title="О себе",
        description="Биография пользователя для ИИ и интерфейса",
        max_length=4000,
    )
    ui_preferences: Dict[str, Any] = Field(
        default_factory=dict,
        title="UI настройки",
        description="Настройки интерфейса пользователя"
    )
    attrs: Dict[str, Any] = Field(
        default_factory=dict,
        title="Атрибуты",
        description="Дополнительные service-specific данные"
    )
    password_hash: Optional[str] = Field(
        default=None,
        title="Хеш пароля",
        description="Bcrypt-хеш; используется только для демо-учётки (auth.demo), не для OAuth",
        groups={"admin": {"hidden": True}, "user": {"hidden": True}},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания пользователя",
        readonly=True,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время последнего обновления",
        readonly=True,
    )


class Company(BaseModel):
    """
    Модель компании (хранится в company:company_id).
    Компания содержит свою собственную изолированную конфигурацию.
    """

    model_config = ConfigDict(
        json_schema_extra={"storage_prefix": "company"}
    )

    company_id: str = Field(
        title="ID компании",
        description="Уникальный ID компании",
        readonly=True,
    )
    name: str = Field(
        title="Название",
        description="Название компании",
        placeholder="Моя компания",
    )
    subdomain: Optional[str] = Field(
        default=None,
        title="Поддомен",
        description="Поддомен компании (company.humanitec.ru)",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    owner_user_id: Optional[str] = Field(
        default=None,
        title="Владелец",
        description="ID пользователя-владельца компании",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    members: Dict[str, List[str]] = Field(
        default_factory=dict,
        title="Участники",
        description="user_id -> [role1, role2]",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    status: str = Field(
        default="active",
        title="Статус",
        description="Статус компании (active, suspended)",
        groups={"admin": {"editable_in_table": True}, "user": {"readonly": True}},
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные данные компании",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    tariff_plan: TariffPlan = Field(
        default=TariffPlan.FREE,
        title="Тарифный план",
        description="Тарифный план компании (free, basic, premium, enterprise)",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    balance: float = Field(
        default=50.0,
        title="Баланс",
        description="Баланс компании в RUB; отрицательное значение — задолженность после списаний",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    monthly_budget: float = Field(
        default=0.0,
        title="Месячный лимит",
        description="Месячное самоограничение в RUB (0 = без самоограничения)",
        ge=0.0,
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )
    current_month_spent: float = Field(
        default=0.0,
        title="Потрачено в месяце",
        description="Потрачено компанией в текущем месяце в RUB",
        readonly=True,
        ge=0.0,
    )
    billing_period_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        title="Начало расчетного периода",
        description="Начало текущего расчетного периода",
        readonly=True,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создана",
        description="Время создания компании",
        readonly=True,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлена",
        description="Время последнего обновления",
        readonly=True,
    )


class AuthSession(BaseModel):
    """Модель сессии авторизации"""

    session_id: str = Field(
        title="ID сессии", 
        description="Уникальный ID сессии авторизации", 
        readonly=True
    )
    user_id: str = Field(
        title="ID пользователя", 
        description="Ссылка на пользователя", 
        readonly=True
    )
    provider: AuthProvider = Field(
        title="Провайдер", 
        description="Провайдер авторизации", 
        readonly=True
    )
    access_token: Optional[str] = Field(
        default=None,
        title="Токен доступа",
        description="Токен доступа от провайдера",
        groups={"admin": {"hidden": False}, "user": {"hidden": True}},
    )
    refresh_token: Optional[str] = Field(
        default=None,
        title="Refresh токен",
        description="Refresh токен от провайдера",
        groups={"admin": {"hidden": False}, "user": {"hidden": True}},
    )
    expires_at: Optional[str] = Field(
        default=None,
        title="Истекает",
        description="Время истечения сессии (ISO строка)",
        readonly=True,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создана",
        description="Время создания сессии",
        readonly=True,
    )
    last_activity: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Последняя активность",
        description="Время последней активности",
        readonly=True,
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные данные сессии",
        groups={"admin": {"readonly": False}, "user": {"readonly": True}},
    )


class ProviderUserInfo(BaseModel):
    """Информация о пользователе от провайдера"""

    provider_user_id: str = Field(description="ID пользователя у провайдера")
    email: str = Field(description="Email пользователя")
    name: str = Field(description="Имя пользователя")
    avatar_url: Optional[str] = Field(default=None, description="URL аватара")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Сырые данные от провайдера")


class AuthRequest(BaseModel):
    """Запрос на завершение авторизации"""
    
    provider: AuthProvider = Field(description="Провайдер авторизации")
    code: str = Field(description="Код авторизации от провайдера")
    state: str = Field(description="State для проверки CSRF")
    redirect_uri: Optional[str] = Field(default=None, description="URI для редиректа")
    oauth_first_login_user_json: Optional[str] = Field(
        default=None,
        description="Apple: JSON из query-параметра user при первой авторизации (имя)",
    )


class NamespaceCRMSettings(BaseModel):
    """Настройки CRM для namespace (заметки: голос, контекст, метаданные интеграций)."""

    show_note_voice_ui: bool = Field(default=True, title="Показывать выбор голоса")
    default_note_voice: Literal["self", "none", "last"] = Field(
        default="self",
        title="Голос по умолчанию для новой заметки",
    )
    default_context_entity_id: Optional[str] = Field(
        default=None,
        title="Якорь контекста по умолчанию",
    )
    integrations: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        title="Метаданные интеграций по ключу провайдера",
        description="Только отображение и подсказки; секреты хранятся в OAuth credentials.",
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_amocrm_subdomain_into_integrations(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        legacy = migrated.pop("amocrm_subdomain", None)
        integ = dict(migrated.get("integrations") or {})
        if legacy is not None and isinstance(legacy, str) and legacy.strip():
            amo = dict(integ.get("amocrm") or {})
            cur = amo.get("subdomain")
            if not (isinstance(cur, str) and cur.strip()):
                amo["subdomain"] = legacy.strip()
            integ["amocrm"] = amo
        migrated["integrations"] = integ
        return migrated


class NamespaceSyncSettings(BaseModel):
    """Настройки Sync для namespace (поведение каналов и звонков пространства)."""

    transcribe_voice_messages: bool = Field(
        default=False,
        title="Авто-расшифровка голосовых",
        description="Автоматически отправлять голосовые сообщения на STT после загрузки",
    )
    speech_to_chat_enabled: bool = Field(
        default=False,
        title="Речь звонка в ленту",
        description="Постить расшифрованные сегменты речи звонка как сообщения в ленту канала",
    )


class Namespace(BaseModel):
    """
    Namespace (изолированная область данных).
    Используется всеми сервисами для организации данных внутри компании.
    """
    model_config = ConfigDict(
        json_schema_extra={"storage_prefix": "namespace"}
    )
    
    name: str = Field(
        title="Название",
        description="Имя namespace (например 'default', 'sales')"
    )
    company_id: str = Field(
        title="ID компании",
        description="ID компании-владельца"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание namespace"
    )
    is_default: bool = Field(
        default=False,
        title="По умолчанию",
        description="Является ли namespace дефолтным для компании"
    )
    crm_settings: Optional[NamespaceCRMSettings] = Field(
        default=None,
        title="Настройки CRM",
        description="Опционально: UI заметок и значения по умолчанию",
    )
    sync_settings: Optional[NamespaceSyncSettings] = Field(
        default=None,
        title="Настройки Sync",
        description="Опционально: дефолты транскрипции и речи в ленту для каналов пространства",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания namespace"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время последнего обновления namespace"
    )


class AuthResult(BaseModel):
    """Результат авторизации"""

    success: bool = Field(description="Успешность авторизации")
    user: Optional[User] = Field(default=None, description="Авторизованный пользователь")
    session: Optional[AuthSession] = Field(default=None, description="Сессия авторизации")
    token: Optional[str] = Field(default=None, description="JWT токен")
    error_message: Optional[str] = Field(default=None, description="Сообщение об ошибке")
    redirect_url: Optional[str] = Field(default=None, description="URL для редиректа")

