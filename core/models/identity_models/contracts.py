"""
Модели для системы идентификации и авторизации.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


ANONYMOUS_USER_ID = "anonymous"
GUEST_USER_ID_PREFIX = "guest:"
SYSTEM_COMPANY_ID = "system"
"""Компания платформы: системный tenant админов и событий вне контекста компании."""


def is_platform_user_id(user_id: str) -> bool:
    """Идентичность из реестра пользователей: не аноним и не гость звонка по ссылке."""
    return user_id not in ("", ANONYMOUS_USER_ID) and not user_id.startswith(GUEST_USER_ID_PREFIX)





class ProviderUserInfo(BaseModel):
    """Информация о пользователе от провайдера"""

    provider_user_id: str = Field(description="ID пользователя у провайдера")
    email: str = Field(description="Email пользователя")
    name: str = Field(description="Имя пользователя")
    avatar_url: str | None = Field(default=None, description="URL аватара")
    raw_data: JsonObject = Field(default_factory=dict, description="Сырые данные от провайдера")



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


_ = SidebarNavEntry.model_rebuild()


