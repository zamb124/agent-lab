"""
Модели для системы идентификации и авторизации.
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Literal, Self, override

from oxyde import Field as DbField
from oxyde import Index, atomic, execute_raw
from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.models.billing_models import TariffPlan
from core.models.platform_model import CompanyScopedModel, PlatformModel
from core.types import JsonObject, parse_json_object, require_json_object


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


ANONYMOUS_USER_ID = "anonymous"
GUEST_USER_ID_PREFIX = "guest:"
SYSTEM_COMPANY_ID = "system"
"""Компания платформы: системный tenant админов и событий вне контекста компании."""


def is_platform_user_id(user_id: str) -> bool:
    """Идентичность из реестра пользователей: не аноним и не гость звонка по ссылке."""
    return user_id not in ("", ANONYMOUS_USER_ID) and not user_id.startswith(GUEST_USER_ID_PREFIX)


class User(PlatformModel):
    """Пользователь. Глобальная таблица ``users`` в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(json_schema_extra={"storage_prefix": "user"})

    user_id: str = DbField(
        db_pk=True,
        title="ID пользователя",
        description="Уникальный ID пользователя в системе",
        json_schema_extra={"readonly": True},
    )

    class Meta:
        is_table: bool = True
        table_name: str = "users"

    name: str = DbField(
        title="Имя",
        description="Отображаемое имя; при сохранении ФИО может выставляться из имени и фамилии",
        max_length=200,
        json_schema_extra={"placeholder": "Иван Иванов"},
    )
    first_name: str | None = Field(
        default=None,
        title="Имя",
        description="Имя для профиля и сопоставления на графе",
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        title="Фамилия",
        description="Фамилия для профиля и сопоставления на графе",
        max_length=100,
    )
    status: UserStatus = Field(
        default=UserStatus.ACTIVE,
        title="Статус",
        description="Статус пользователя",
        json_schema_extra={
            "groups": {"admin": {"editable_in_table": True}, "user": {"readonly": True}}
        },
    )
    groups: list[str] = Field(
        default_factory=lambda: ["user"],
        title="Группы",
        description="Группы пользователя (admin, user, bot_editor, guest)",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    companies: dict[str, list[str]] = Field(
        default_factory=dict,
        title="Компании и роли",
        description="company_id -> [role1, role2]",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    active_company_id: str = Field(
        default="",
        title="Активная компания",
        description="ID текущей активной компании",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    emails: list[str] = Field(
        default_factory=list, title="Email адреса", description="Список email адресов пользователя"
    )

    @property
    def email(self) -> str:
        """Первый email для JWT и вызовов, где ожидается одна строка."""
        if not self.emails:
            return ""
        return self.emails[0]

    phones: list[str] = Field(
        default_factory=list, title="Телефоны", description="Список телефонных номеров"
    )
    messengers: dict[str, str] = Field(
        default_factory=dict,
        title="Мессенджеры",
        description="Контакты в мессенджерах: {telegram: @username, whatsapp: +123, slack: U12345}",
    )
    avatar_url: str | None = Field(
        default=None, title="Аватар", description="URL аватара пользователя"
    )
    bio: str | None = Field(
        default=None,
        title="О себе",
        description="Биография пользователя для ИИ и интерфейса",
        max_length=4000,
    )
    ui_preferences: JsonObject = Field(
        default_factory=dict, title="UI настройки", description="Настройки интерфейса пользователя"
    )
    attributes: JsonObject = Field(
        default_factory=dict,
        title="Атрибуты",
        description="Дополнительные service-specific данные",
    )
    password_hash: str | None = Field(
        default=None,
        title="Хеш пароля",
        description="Bcrypt-хеш; используется только для демо-учётки (auth.demo), не для OAuth",
        json_schema_extra={"groups": {"admin": {"hidden": True}, "user": {"hidden": True}}},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания пользователя",
        json_schema_extra={"readonly": True},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время последнего обновления",
        json_schema_extra={"readonly": True},
    )

    @classmethod
    async def find_by_email(cls, email: str) -> User | None:
        matches = await cls.find_all_by_email_ci(email)
        if not matches:
            return None
        return matches[0]

    @classmethod
    async def find_all_by_email_ci(cls, email: str) -> list[User]:
        norm = email.strip().lower()
        if not norm:
            raise ValueError("search email cannot be empty")
        table = cls.get_table_name()
        rows = await execute_raw(
            f"""
            SELECT row_to_json({table}) AS item
            FROM {table}
            WHERE EXISTS (
                SELECT 1 FROM unnest(emails) AS email
                WHERE lower(email) = $1
            )
            ORDER BY user_id
            """,
            [norm],
            using="shared",
        )
        return [_user_from_row(row) for row in rows]

    @classmethod
    async def search_by_query(cls, query: str, limit: int = 20) -> list[User]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        table = cls.get_table_name()
        pattern = _like_contains(query)
        rows = await execute_raw(
            f"""
            SELECT row_to_json({table}) AS item
            FROM {table}
            WHERE name ILIKE $1 ESCAPE '\\'
               OR EXISTS (
                    SELECT 1 FROM unnest(emails) AS email
                    WHERE email ILIKE $1 ESCAPE '\\'
               )
            ORDER BY user_id
            LIMIT $2
            """,
            [pattern, limit],
            using="shared",
        )
        return [_user_from_row(row) for row in rows]


def _like_contains(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _user_from_row(row: object) -> User:
    parsed = require_json_object(row, "user")
    raw_item = parsed["item"] if "item" in parsed else parsed
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "user")
    else:
        payload = require_json_object(raw_item, "user")
    return User.model_validate(payload)


class Company(PlatformModel):
    """Компания. Глобальная таблица ``companies`` в ``platform_shared``.

    ``members`` — JSON-поле этой модели: состав ролей читается вместе с компанией.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    company_id: str = DbField(
        db_pk=True,
        title="ID компании",
        description="Уникальный ID компании",
        json_schema_extra={"readonly": True},
    )

    class Meta:
        is_table: bool = True
        table_name: str = "companies"
        indexes: list[Index] = [
            Index(["subdomain"], unique=True, where="subdomain IS NOT NULL"),
        ]

    name: str = DbField(
        title="Название",
        description="Название компании",
        json_schema_extra={"placeholder": "Моя компания"},
    )
    subdomain: str | None = DbField(
        default=None,
        title="Поддомен",
        description="Поддомен компании (company.humanitec.ru)",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    owner_user_id: str | None = Field(
        default=None,
        title="Владелец",
        description="ID пользователя-владельца компании",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    members: dict[str, list[str]] = Field(
        default_factory=dict,
        title="Участники",
        description="user_id -> [role1, role2]",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    status: str = Field(
        default="active",
        title="Статус",
        description="Статус компании (active, suspended)",
        json_schema_extra={
            "groups": {"admin": {"editable_in_table": True}, "user": {"readonly": True}}
        },
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные данные компании",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    tariff_plan: TariffPlan = Field(
        default=TariffPlan.FREE,
        title="Тарифный план",
        description="Тарифный план компании (free, basic, premium, enterprise)",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    balance: float = Field(
        default=50.0,
        title="Баланс",
        description="Баланс компании в RUB; отрицательное значение — задолженность после списаний",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    monthly_budget: float = Field(
        default=0.0,
        title="Месячный лимит",
        description="Месячное самоограничение в RUB (0 = без самоограничения)",
        ge=0.0,
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )
    current_month_spent: float = Field(
        default=0.0,
        title="Потрачено в месяце",
        description="Потрачено компанией в текущем месяце в RUB",
        ge=0.0,
        json_schema_extra={"readonly": True},
    )
    billing_period_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ),
        title="Начало расчетного периода",
        description="Начало текущего расчетного периода",
        json_schema_extra={"readonly": True},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создана",
        description="Время создания компании",
        json_schema_extra={"readonly": True},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлена",
        description="Время последнего обновления",
        json_schema_extra={"readonly": True},
    )

    @classmethod
    async def page_named_after_system(
        cls, *, limit: int, offset: int
    ) -> tuple[list[Self], bool]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        system = await cls.get(SYSTEM_COMPANY_ID)
        if system is None:
            raise ValueError("system company is required")
        if offset == 0:
            head = [system]
            rest_offset = 0
            rest_limit = limit - 1
        else:
            head = []
            rest_offset = offset - 1
            rest_limit = limit
        rest = await (
            cls.objects.exclude(company_id=SYSTEM_COMPANY_ID)
            .order_by("name", "company_id")
            .limit(rest_limit + 1)
            .offset(rest_offset)
            .all()
        )
        has_more = len(rest) > rest_limit
        return [*head, *rest[:rest_limit]], has_more

    @classmethod
    async def by_subdomain(cls, subdomain: str) -> Self | None:
        if subdomain == "":
            raise ValueError("subdomain is required")
        return await cls.objects.filter(subdomain=subdomain).get_or_none()

    @classmethod
    async def put_member_roles(
        cls,
        company_id: str,
        user_id: str,
        roles: Sequence[str],
    ) -> Self:
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not user_id.strip():
            raise ValueError("user_id is required")
        normalized = [role.strip() for role in roles if role.strip()]
        if not normalized:
            raise ValueError("company membership roles must be non-empty")
        async with atomic(using="shared"):
            company = await cls.objects.filter(company_id=company_id).for_update().get()
            members = dict(company.members)
            members[user_id] = list(normalized)
            company.members = members
            _ = await company.save(update_fields=["members"])
            return company

    @classmethod
    async def add_balance(cls, company_id: str, amount: float) -> Self:
        if company_id == "":
            raise ValueError("company_id is required")
        async with atomic(using="shared"):
            company = await cls.objects.filter(company_id=company_id).for_update().get_or_none()
            if company is None:
                raise ValueError(f"Company {company_id} not found")
            company.balance += amount
            _ = await company.save(update_fields=["balance"])
            return company

    @classmethod
    async def discard_member(cls, company_id: str, user_id: str) -> Self:
        if not company_id.strip():
            raise ValueError("company_id is required")
        if not user_id.strip():
            raise ValueError("user_id is required")
        async with atomic(using="shared"):
            company = await cls.objects.filter(company_id=company_id).for_update().get()
            if user_id not in company.members:
                raise ValueError(f"company member not found: {user_id}")
            members = dict(company.members)
            del members[user_id]
            company.members = members
            _ = await company.save(update_fields=["members"])
            return company


class AuthSession(PlatformModel):
    """Сессия входа. Глобальная таблица ``auth_sessions`` в ``platform_shared``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    session_id: str = DbField(
        db_pk=True,
        title="ID сессии",
        description="Уникальный ID сессии авторизации",
        json_schema_extra={"readonly": True},
    )

    class Meta:
        is_table: bool = True
        table_name: str = "auth_sessions"

    user_id: str = DbField(
        db_index=True,
        title="ID пользователя",
        description="Ссылка на пользователя",
        json_schema_extra={"readonly": True},
    )
    provider: AuthProvider = DbField(
        title="Провайдер", description="Провайдер авторизации", json_schema_extra={"readonly": True}
    )
    access_token: str | None = Field(
        default=None,
        title="Токен доступа",
        description="Токен доступа от провайдера",
        json_schema_extra={"groups": {"admin": {"hidden": False}, "user": {"hidden": True}}},
    )
    refresh_token: str | None = Field(
        default=None,
        title="Refresh токен",
        description="Refresh токен от провайдера",
        json_schema_extra={"groups": {"admin": {"hidden": False}, "user": {"hidden": True}}},
    )
    expires_at: str | None = Field(
        default=None,
        title="Истекает",
        description="Время истечения сессии (ISO строка)",
        json_schema_extra={"readonly": True},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создана",
        description="Время создания сессии",
        json_schema_extra={"readonly": True},
    )
    last_activity: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Последняя активность",
        description="Время последней активности",
        json_schema_extra={"readonly": True},
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        title="Метаданные",
        description="Дополнительные данные сессии",
        json_schema_extra={"groups": {"admin": {"readonly": False}, "user": {"readonly": True}}},
    )


class ProviderUserInfo(BaseModel):
    """Информация о пользователе от провайдера"""

    provider_user_id: str = Field(description="ID пользователя у провайдера")
    email: str = Field(description="Email пользователя")
    name: str = Field(description="Имя пользователя")
    avatar_url: str | None = Field(default=None, description="URL аватара")
    raw_data: JsonObject = Field(default_factory=dict, description="Сырые данные от провайдера")


class UserProviderRecord(PlatformModel):
    """Одна связь пользователя с OAuth-провайдером. Таблица ``user_providers``."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    user_provider_id: str = DbField(db_pk=True, description="provider_name:provider_user_id")
    user_id: str = DbField(db_index=True, description="Пользователь платформы")
    provider_user_id: str = DbField(db_index=True, description="ID пользователя у провайдера")
    provider_name: AuthProvider = DbField(description="Провайдер авторизации")

    class Meta:
        is_table: bool = True
        table_name: str = "user_providers"
        unique_together: list[tuple[str, str]] = [("provider_name", "provider_user_id")]

    email: str = DbField(description="Email пользователя у провайдера")
    avatar_url: str | None = Field(default=None, description="URL аватара у провайдера")
    metadata: JsonObject = Field(default_factory=dict, description="Данные профиля провайдера")

    @classmethod
    async def find_by_provider_user_id(cls, provider_user_id: str) -> Self | None:
        if provider_user_id == "":
            raise ValueError("provider_user_id is required")
        return await cls.objects.filter(provider_user_id=provider_user_id).first()

    @classmethod
    async def list_by_user_id(cls, user_id: str) -> list[Self]:
        if user_id == "":
            raise ValueError("user_id is required")
        return await cls.objects.filter(user_id=user_id).all()


class AuthRequest(BaseModel):
    """Запрос на завершение авторизации"""

    provider: AuthProvider = Field(description="Провайдер авторизации")
    code: str = Field(description="Код авторизации от провайдера")
    state: str = Field(description="State для проверки CSRF")
    redirect_uri: str | None = Field(default=None, description="URI для редиректа")
    oauth_first_login_user_json: str | None = Field(
        default=None,
        description="Apple: JSON из query-параметра user при первой авторизации (имя)",
    )


class AuthState(BaseModel):
    """Временное OAuth state, сохраненное между start_auth и callback."""

    provider: AuthProvider = Field(description="Провайдер авторизации")
    redirect_uri: str = Field(description="OAuth redirect_uri, использованный при старте")
    original_host: str | None = Field(default=None, description="Хост, с которого начат вход")
    return_path: str | None = Field(default=None, description="Путь возврата после входа")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Время создания state",
    )


class AuthCodeCache(BaseModel):
    """Кеш результата OAuth callback для одноразового provider code."""

    user_id: str = Field(description="ID авторизованного пользователя")
    session_id: str = Field(description="ID созданной auth-сессии")
    token: str = Field(description="JWT, выпущенный для callback")


class SidebarNavEntry(BaseModel):
    """Элемент дерева бокового меню пространства (NetWorkle).

    Лист: задан ``route_key``. Группа: непустой ``children``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    nav_id: str = Field(min_length=1, description="Стабильный id для active state и редактора")
    label: str = Field(description="Подпись пункта")
    icon: str | None = Field(default=None, description="Имя иконки platform-icon")
    route_key: str | None = Field(default=None, description="Ключ маршрута SPA (лист)")
    search: str = Field(
        default="",
        description="Query с ведущим ? для history",
    )
    children: list["SidebarNavEntry"] = Field(default_factory=list)

    @model_validator(mode="after")
    def _leaf_or_group(self) -> "SidebarNavEntry":
        has_children = len(self.children) > 0
        rk = (self.route_key or "").strip()
        if bool(has_children):
            if bool(rk):
                raise ValueError('SidebarNavEntry: group must not set route_key')
            sch = (self.search or "").strip()
            if bool(sch):
                raise ValueError('SidebarNavEntry: group must not set search')
        else:
            if not bool(rk):
                raise ValueError('SidebarNavEntry: leaf requires a non-empty route_key')
        return self


class NamespaceAutomationRule(BaseModel):
    """Правило автоматизации пространства (контракт хранения; исполнитель — flows/scheduler)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    rule_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    trigger: str = Field(min_length=1, description="entity_created | stage_changed | …")
    action: str = Field(min_length=1, description="run_flow | notify | …")
    flow_id: str | None = Field(default=None)


class SuggestsSettings(BaseModel):
    """Настройки фоновой генерации саджестов (дубли/пропущенные)."""

    enabled: bool = Field(default=False, title="Включить фоновый поиск саджестов")
    cron: str = Field(default="0 2 * * *", title="Cron-расписание для генерации")
    schedule_task_id: str | None = Field(
        default=None, description="ID платформенной задачи расписания"
    )


class NamespaceCRMSettings(BaseModel):
    """Настройки CRM для namespace (заметки: голос, контекст, метаданные интеграций)."""

    show_note_voice_ui: bool = Field(default=True, title="Показывать выбор голоса")
    default_note_voice: Literal["self", "none", "last"] = Field(
        default="self",
        title="Голос по умолчанию для новой заметки",
    )
    default_context_entity_id: str | None = Field(
        default=None,
        title="Якорь контекста по умолчанию",
    )
    integrations: dict[str, JsonObject] = Field(
        default_factory=dict,
        title="Метаданные интеграций по ключу провайдера",
        description=(
            "Только отображение и подсказки; секреты хранятся в OAuth credentials. "
            "Для автосинка (если поддерживает коннектор): auto_sync_enabled, auto_sync_cron, "
            "auto_sync_timezone, auto_sync_schedule_task_id, auto_sync_oauth_user_id."
        ),
    )
    sidebar_navigation: list[SidebarNavEntry] | None = Field(
        default=None,
        title="Дерево основного меню сайдбара",
        description="None: клиент строит меню из типов пространства",
    )
    default_flow_by_entity_type: dict[str, str] = Field(
        default_factory=dict,
        title="Идентификатор flow по умолчанию для типа сущности",
    )
    automation_rules: list[NamespaceAutomationRule] = Field(default_factory=list)
    suggests: SuggestsSettings = Field(
        default_factory=SuggestsSettings,
        title="Настройки саджестов",
    )


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


class NamespaceKind(str, Enum):
    """Вид платформенного namespace (company workspace / personal / technical)."""

    COMPANY_WORKSPACE = "company_workspace"
    PERSONAL = "personal"
    TECHNICAL = "technical"


class Namespace(CompanyScopedModel):
    """Пространство компании. Таблица ``namespaces`` в ``platform_shared``.

    Внутри компании пространство адресуется ``name``. Первичный ключ строки —
    ``namespace_id`` = ``company_id:name``, чтобы ``default`` мог быть у каждой компании.
    """

    __database_alias__: ClassVar[str | None] = "shared"

    namespace_id: str = DbField(default="", db_pk=True)
    name: str = DbField(
        db_index=True,
        title="Название",
        description="Имя namespace (например 'default', 'sales')",
    )
    company_id: str = DbField(db_index=True, title="ID компании", description="ID компании-владельца")

    class Meta:
        is_table: bool = True
        table_name: str = "namespaces"
        unique_together: list[tuple[str, str]] = [("company_id", "name")]

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        self.namespace_id = f"{self.company_id}:{self.name}"
    description: str | None = Field(
        default=None, title="Описание", description="Описание namespace"
    )
    is_default: bool = Field(
        default=False,
        title="По умолчанию",
        description="Является ли namespace дефолтным для компании",
    )
    kind: NamespaceKind = Field(
        default=NamespaceKind.COMPANY_WORKSPACE,
        title="Вид",
        description="company_workspace | personal | technical",
    )
    owner_user_id: str | None = Field(
        default=None,
        title="Владелец",
        description="user_id владельца; обязателен для kind=personal",
    )
    crm_settings: NamespaceCRMSettings | None = DbField(
        default=None,
        db_type="JSONB",
        title="Настройки CRM",
        description="Опционально: UI заметок и значения по умолчанию",
    )
    sync_settings: NamespaceSyncSettings | None = DbField(
        default=None,
        db_type="JSONB",
        title="Настройки Sync",
        description="Опционально: дефолты транскрипции и речи в ленту для каналов пространства",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания namespace",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время последнего обновления namespace",
    )

    @model_validator(mode="after")
    def _validate_personal_owner(self) -> "Namespace":
        if self.kind == NamespaceKind.PERSONAL:
            if self.owner_user_id is None or self.owner_user_id.strip() == "":
                raise ValueError("owner_user_id is required for kind=personal")
            if self.is_default:
                raise ValueError("personal namespace cannot be is_default")
        elif self.owner_user_id is not None:
            raise ValueError("owner_user_id is only allowed for kind=personal")
        return self

    @classmethod
    async def by_name(cls, name: str) -> Self | None:
        return await cls.objects.filter(name=name).get_or_none()

    @classmethod
    async def delete_by_name(cls, name: str) -> bool:
        deleted = await cls.objects.filter(name=name).delete()
        return deleted > 0

    @classmethod
    async def list_by_kind(
        cls,
        kinds: list[NamespaceKind],
        *,
        limit: int,
        offset: int,
    ) -> list[Self]:
        return await (
            cls.objects.filter(kind__in=kinds)
            .order_by("name")
            .limit(limit)
            .offset(offset)
            .all()
        )

    @classmethod
    async def count_by_kind(cls, kinds: list[NamespaceKind]) -> int:
        return await cls.objects.filter(kind__in=kinds).count()

    @classmethod
    async def list_for_authz(cls, *, limit: int | None) -> list[Self]:
        # Живая таблица ещё key/value. Менеджер отрезал бы одну компанию.
        sql = (
            "SELECT value->>'name' AS name, "
            "value->>'company_id' AS company_id, "
            "value->>'kind' AS kind, "
            "value->>'owner_user_id' AS owner_user_id "
            "FROM namespaces "
            "WHERE value->>'company_id' IS NOT NULL "
            "AND value->>'name' IS NOT NULL "
            "ORDER BY key"
        )
        params: list[int] = []
        if limit is not None:
            sql = f"{sql} LIMIT $1"
            params = [limit]
        rows = await execute_raw(sql, params, using="shared")
        namespaces: list[Self] = []
        for row in rows:
            parsed = require_json_object(row, "namespace")
            name = parsed["name"]
            company_id = parsed["company_id"]
            if not isinstance(name, str) or name == "":
                raise ValueError("namespaces.name is required")
            if not isinstance(company_id, str) or company_id == "":
                raise ValueError("namespaces.company_id is required")
            kind = NamespaceKind.COMPANY_WORKSPACE
            kind_cell = parsed["kind"]
            if kind_cell == NamespaceKind.PERSONAL.value:
                kind = NamespaceKind.PERSONAL
            elif kind_cell == NamespaceKind.TECHNICAL.value:
                kind = NamespaceKind.TECHNICAL
            owner_user_id: str | None = None
            owner_cell = parsed["owner_user_id"]
            if isinstance(owner_cell, str) and owner_cell.strip() != "":
                owner_user_id = owner_cell.strip()
            if kind == NamespaceKind.PERSONAL and owner_user_id is None:
                raise ValueError(
                    f"personal namespace {name} missing owner_user_id for backfill"
                )
            if kind != NamespaceKind.PERSONAL:
                owner_user_id = None
            namespaces.append(
                cls.model_validate(
                    {
                        "name": name,
                        "company_id": company_id,
                        "kind": kind,
                        "owner_user_id": owner_user_id,
                    }
                )
            )
        return namespaces


class AuthResult(BaseModel):
    """Результат авторизации"""

    success: bool = Field(description="Успешность авторизации")
    user: User | None = Field(default=None, description="Авторизованный пользователь")
    session: AuthSession | None = Field(default=None, description="Сессия авторизации")
    token: str | None = Field(default=None, description="JWT токен")
    error_message: str | None = Field(default=None, description="Сообщение об ошибке")
    redirect_url: str | None = Field(default=None, description="URL для редиректа")


_ = SidebarNavEntry.model_rebuild()
