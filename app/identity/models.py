"""
Модели для системы авторизации.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class UserStatus(str, Enum):
    """Статус пользователя"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"


class AuthProvider(str, Enum):
    """Перечисление доступных провайдеров авторизации."""

    YANDEX = "yandex"
    GOOGLE = "google"
    GITHUB = "github"


class User(BaseModel):
    """
    Основная модель пользователя (хранится в user:user_id).
    Содержит только общие данные, без привязки к провайдерам.
    """

    class Config:
        storage_prefix = "user"

    user_id: str = Field(
        title="ID пользователя",
        description="Уникальный ID пользователя в системе",
        readonly=True,
    )
    name: str = Field(
        title="Имя", 
        description="Имя пользователя", 
        placeholder="Иван Иванов"
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


class AuthSession(BaseModel):
    """Модель сессии авторизации"""

    session_id: str = Field(
        title="ID сессии", description="Уникальный ID сессии авторизации", readonly=True
    )
    user_id: str = Field(
        title="ID пользователя", description="Ссылка на пользователя", readonly=True
    )
    provider: AuthProvider = Field(
        title="Провайдер", description="Провайдер авторизации", readonly=True
    )
    access_token: Optional[str] = Field(
        default=None,
        title="Токен доступа",
        description="Токен доступа от провайдера",
        groups={"admin": {"hidden": False}, "user": {"hidden": True}},
    )
    refresh_token: Optional[str] = Field(
        default=None,
        title="Токен обновления",
        description="Токен обновления",
        groups={"admin": {"hidden": False}, "user": {"hidden": True}},
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        title="Истекает",
        description="Время истечения токена",
        readonly=True,
    )
    session_data: Dict[str, Any] = Field(
        default_factory=dict,
        title="Данные сессии",
        description="Дополнительные данные сессии",
        groups={"admin": {"hidden": False}, "user": {"hidden": True}},
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


class ProviderUserInfo(BaseModel):
    """Информация о пользователе от провайдера"""

    provider_user_id: str = Field(
        title="ID у провайдера",
        description="ID пользователя у провайдера",
        readonly=True,
    )
    email: str = Field(
        title="Email", description="Электронная почта пользователя", readonly=True
    )
    name: str = Field(title="Имя", description="Имя пользователя", readonly=True)
    avatar_url: Optional[str] = Field(
        default=None,
        title="URL аватара",
        description="URL изображения аватара",
        readonly=True,
    )
    raw_data: Dict[str, Any] = Field(
        default_factory=dict,
        title="Исходные данные",
        description="Исходные данные от провайдера",
        readonly=True,
    )


class AuthResult(BaseModel):
    """Результат авторизации"""

    success: bool = Field(
        title="Успех", description="Успешность авторизации", readonly=True
    )
    user: Optional[User] = Field(
        default=None,
        title="Пользователь",
        description="Авторизованный пользователь",
        readonly=True,
    )
    session: Optional[AuthSession] = Field(
        default=None, title="Сессия", description="Сессия авторизации", readonly=True
    )
    token: Optional[str] = Field(
        default=None, title="Токен", description="Токен доступа", readonly=True
    )
    error_message: Optional[str] = Field(
        default=None,
        title="Сообщение об ошибке",
        description="Сообщение об ошибке при авторизации",
        readonly=True,
    )
    redirect_url: Optional[str] = Field(
        default=None,
        title="URL редиректа",
        description="URL для редиректа после авторизации",
        readonly=True,
    )


class Company(BaseModel):
    """Модель компании"""

    class Config:
        storage_prefix = "company"

    company_id: str = Field(title="ID компании", readonly=True)
    subdomain: str = Field(title="Поддомен", description="Уникальный поддомен компании")
    name: str = Field(title="Название компании")
    status: str = Field(default="active", title="Статус компании")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создана",
        readonly=True,
    )
    
    # Поля для биллинга и тарификации
    tariff_plan: str = Field(
        default="free",
        title="Тарифный план",
        description="Тарифный план компании (free, basic, premium, enterprise)"
    )
    balance: float = Field(
        default=50.0,
        title="Баланс",
        description="Баланс компании в RUB (реальные деньги на счету)",
        ge=0.0
    )
    monthly_budget: float = Field(
        default=0.0,
        title="Месячный лимит",
        description="Месячное самоограничение в RUB (0 = без самоограничения)",
        ge=0.0
    )
    current_month_spent: float = Field(
        default=0.0,
        title="Потрачено в месяце",
        description="Потрачено компанией в текущем месяце в RUB",
        readonly=True,
        ge=0.0
    )
    billing_period_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0),
        title="Начало расчетного периода",
        description="Начало текущего расчетного периода",
        readonly=True
    )
    
    payment_provider: Optional[str] = Field(
        default=None,
        title="Платежный провайдер",
        description="Платежный провайдер для пополнения баланса (yoomoney, yukassa). None = использовать дефолтный"
    )


class CreateCompanyForm(BaseModel):
    """Форма создания компании"""

    class Config:
        storage_prefix = "create_company_form"

    name: str = Field(
        default="",
        title="Название компании",
        description="Введите название вашей компании",
        placeholder="Моя компания"
    )
    slug: str = Field(
        title="Slug компании",
        description="Уникальный идентификатор для URL (только латинские буквы и цифры)",
        placeholder="mycompany",
        min_length=3,
        max_length=20,
        pattern=r"^[a-z0-9]+$"
    )


class AuthRequest(BaseModel):
    """Запрос на авторизацию"""

    provider: AuthProvider = Field(
        title="Провайдер",
        description="Провайдер авторизации",
    )
    code: Optional[str] = Field(
        default=None,
        title="Код авторизации",
        description="Код авторизации от провайдера",
    )
    state: Optional[str] = Field(
        default=None,
        title="State",
        description="State для защиты от CSRF",
    )
    redirect_uri: Optional[str] = Field(
        default=None,
        title="URI редиректа",
        description="URI для редиректа",
    )
