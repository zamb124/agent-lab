"""
Модели для системы идентификации и авторизации.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.models.billing_models import TariffPlan
from core.types import JsonObject


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

    model_config: ClassVar[ConfigDict] = ConfigDict(json_schema_extra={"storage_prefix": "user"})

    user_id: str = Field(
        title="ID пользователя",
        description="Уникальный ID пользователя в системе",
        json_schema_extra={"readonly": True},
    )
    name: str = Field(
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


class Company(BaseModel):
    """
    Модель компании (хранится в company:company_id).
    Компания содержит свою собственную изолированную конфигурацию.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(json_schema_extra={"storage_prefix": "company"})

    company_id: str = Field(
        title="ID компании",
        description="Уникальный ID компании",
        json_schema_extra={"readonly": True},
    )
    name: str = Field(
        title="Название",
        description="Название компании",
        json_schema_extra={"placeholder": "Моя компания"},
    )
    subdomain: str | None = Field(
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


class AuthSession(BaseModel):
    """Модель сессии авторизации"""

    session_id: str = Field(
        title="ID сессии",
        description="Уникальный ID сессии авторизации",
        json_schema_extra={"readonly": True},
    )
    user_id: str = Field(
        title="ID пользователя",
        description="Ссылка на пользователя",
        json_schema_extra={"readonly": True},
    )
    provider: AuthProvider = Field(
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


class UserProviderRecord(BaseModel):
    """Сохраненная связь пользователя с внешним OAuth-провайдером."""

    provider_name: AuthProvider = Field(description="Провайдер авторизации")
    email: str = Field(description="Email пользователя у провайдера")
    avatar_url: str | None = Field(default=None, description="URL аватара у провайдера")
    metadata: JsonObject = Field(default_factory=dict, description="Данные профиля провайдера")


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


class BoardStage(BaseModel):
    """Стадия канбана задач.

    Значение хранится в attributes.status у CRMEntity с entity_type=task.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Стабильный идентификатор стадии (snake_case)",
    )
    label: str = Field(min_length=1, description="Подпись колонки в UI")
    color: str | None = Field(default=None, description="Опциональный CSS-цвет")


class TaskBoardPreset(BaseModel):
    """Набор колонок доски задач для одного ключа доски (см. task_board_key в CRM)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    stages: list[BoardStage] = Field(min_length=1, description="Упорядоченные стадии слева направо")

    @model_validator(mode="after")
    def _unique_stage_ids(self) -> "TaskBoardPreset":
        ids = [s.id for s in self.stages]
        if len(ids) != len(set(ids)):
            raise ValueError("TaskBoardPreset: повторяющиеся id стадий")
        return self


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
                raise ValueError("SidebarNavEntry: у группы не задают route_key")
            sch = (self.search or "").strip()
            if bool(sch):
                raise ValueError("SidebarNavEntry: у группы не задают search")
        else:
            if not bool(rk):
                raise ValueError("SidebarNavEntry: лист требует непустой route_key")
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
    pipeline_stage_presets: dict[str, TaskBoardPreset] = Field(
        default_factory=dict,
        title="Пресеты колонок доски задач",
        description="Ключ доски (task или task:<subtype>) → упорядоченные стадии. Пусто: резолвер CRM подставляет системный набор.",
    )
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


class Namespace(BaseModel):
    """
    Namespace (изолированная область данных).
    Используется всеми сервисами для организации данных внутри компании.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "namespace"}
    )

    name: str = Field(title="Название", description="Имя namespace (например 'default', 'sales')")
    company_id: str = Field(title="ID компании", description="ID компании-владельца")
    description: str | None = Field(
        default=None, title="Описание", description="Описание namespace"
    )
    is_default: bool = Field(
        default=False,
        title="По умолчанию",
        description="Является ли namespace дефолтным для компании",
    )
    crm_settings: NamespaceCRMSettings | None = Field(
        default=None,
        title="Настройки CRM",
        description="Опционально: UI заметок и значения по умолчанию",
    )
    sync_settings: NamespaceSyncSettings | None = Field(
        default=None,
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


class AuthResult(BaseModel):
    """Результат авторизации"""

    success: bool = Field(description="Успешность авторизации")
    user: User | None = Field(default=None, description="Авторизованный пользователь")
    session: AuthSession | None = Field(default=None, description="Сессия авторизации")
    token: str | None = Field(default=None, description="JWT токен")
    error_message: str | None = Field(default=None, description="Сообщение об ошибке")
    redirect_url: str | None = Field(default=None, description="URL для редиректа")


_ = SidebarNavEntry.model_rebuild()
