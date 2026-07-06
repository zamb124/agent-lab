"""
Модели для системы встраиваемых виджетов чата.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from core.models.flow_chat_settings import EmbedChatPolicyOverride


class EmbedStatus(str, Enum):
    """Статус встраиваемого виджета"""
    ACTIVE = "active"
    DISABLED = "disabled"


DEFAULT_EMBED_INPUT_PLACEHOLDER = "Введите сообщение..."


class EmbedConfig(BaseModel):
    """
    Конфигурация встраиваемого виджета чата.
    Хранится с префиксом embed_config: в storage компании.

    is_global=False - изоляция по компаниям через префикс company:{company_id}:
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "embed_config"}
    )

    embed_id: str = Field(
        title="ID виджета",
        description="Публичный идентификатор виджета",
        json_schema_extra={"readonly": True},
    )
    name: str = Field(
        title="Название",
        description="Человекочитаемое название виджета",
        json_schema_extra={"placeholder": "Чат на главной странице"},
    )
    flow_id: str = Field(
        title="ID агента",
        description="Агент, который будет отвечать в этом виджете",
    )
    branch_id: str = Field(
        default="default",
        title="Ветка графа",
        description="Точка входа ветки flow (metadata.branch в A2A); для внешних агентов обычно default",
    )
    allowed_origins: list[str] = Field(
        default_factory=list,
        title="Разрешенные домены",
        description="Список доменов, где можно использовать виджет (пусто = любой)",
    )
    status: EmbedStatus = Field(
        default=EmbedStatus.ACTIVE,
        title="Статус",
        description="Статус виджета",
    )

    # Настройки внешнего вида
    theme: str = Field(
        default="dark",
        title="Тема",
        description="Тема оформления (dark, light, auto)",
    )
    position: str = Field(
        default="bottom-right",
        title="Позиция",
        description="Позиция на странице (bottom-right, bottom-left)",
    )
    show_launcher: bool = Field(
        default=True,
        title="Показывать кнопку запуска",
        description="Показывать встроенную FAB кнопку запуска embed-чата",
    )
    primary_color: str = Field(
        default="#6366f1",
        title="Основной цвет",
        description="Основной цвет интерфейса (HEX)",
    )
    assistant_title: str | None = Field(
        default=None,
        title="Имя ассистента",
        description="Кастомное имя ассистента в шапке embed-чата",
    )
    interface_locale: str = Field(
        default="auto",
        title="Язык интерфейса",
        description="Язык интерфейса embed-чата (auto, ru, en)",
    )
    placeholder: str = Field(
        default=DEFAULT_EMBED_INPUT_PLACEHOLDER,
        title="Placeholder",
        description="Текст placeholder в поле ввода",
    )
    branding: bool = Field(
        default=True,
        title="Брендинг",
        description="Показывать брендинг Humanitec",
    )
    landing_visible: bool = Field(
        default=False,
        title="Показ в каталоге лендинга",
        description="Публичный каталог демо-агентов (только привязка компании system и отдельный публичный API)",
    )
    landing_card_image_url: str | None = Field(
        default=None,
        title="Картинка карточки на лендинге",
        description="URL изображения для карточки демо-сотрудника (обязателен при landing_visible)",
    )
    landing_sort_order: int = Field(
        default=0,
        title="Порядок в каталоге лендинга",
        description="Меньше — выше в списке",
    )
    guest_max_user_messages: int | None = Field(
        default=None,
        title="Лимит сообщений гостя (embed-session)",
        description=(
            "Максимум пользовательских сообщений на один диалог (contextId) для токена "
            "embed-session; не задано — без лимита"
        ),
    )
    voice_enabled: bool = Field(
        default=False,
        title="Голосовой режим",
        description=(
            "Разрешить в виджете кнопку голосового режима (WS `/voice/api/ws/session/..` + "
            "bridge к A2A). При False кнопка скрыта, voice_default_on игнорируется."
        ),
    )
    voice_default_on: bool = Field(
        default=False,
        title="Включать голос по умолчанию",
        description=(
            "Запускать голосовой режим автоматически при открытии виджета. "
            "Имеет силу только если voice_enabled=True."
        ),
    )
    preview_share_link: bool = Field(
        default=False,
        title="Служебный виджет для одноразовой гостевой ссылки из редактора flow",
        description="Не показывается в списке embed configs консоли; создаётся только через preview-share API.",
    )
    chat_override: EmbedChatPolicyOverride | None = Field(
        default=None,
        title="Переопределение поведения чата",
        description=(
            "Частичный override FlowChatSettings для этого виджета; "
            "None — полное наследование настроек flow"
        ),
    )

    @field_serializer("chat_override")
    def _serialize_chat_override(
        self,
        value: EmbedChatPolicyOverride | None,
    ) -> dict[str, bool | str | list[str] | None] | None:
        if value is None:
            return None
        payload = value.model_dump(exclude_unset=True)
        if not payload:
            return None
        return payload

    # Статистика
    usage_count: int = Field(
        default=0,
        title="Количество использований",
        description="Счетчик использований виджета",
        json_schema_extra={"readonly": True},
    )
    last_used_at: datetime | None = Field(
        default=None,
        title="Последнее использование",
        description="Время последнего использования",
        json_schema_extra={"readonly": True},
    )

    # Метаданные
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания виджета",
        json_schema_extra={"readonly": True},
    )
    created_by: str = Field(
        title="Создал",
        description="user_id создателя виджета",
        json_schema_extra={"readonly": True},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время последнего обновления",
        json_schema_extra={"readonly": True},
    )


class EmbedChatLook(BaseModel):
    """
    Look&feel-проекция EmbedConfig для доставки в chat-profile.

    Только внешний вид виджета; политика поведения чата живёт в FlowConfig.chat.
    """

    theme: str
    position: str
    primary_color: str
    assistant_title: str | None
    placeholder: str
    interface_locale: str
    show_launcher: bool
    branding: bool
    voice_enabled: bool
    voice_default_on: bool

    @classmethod
    def from_embed_config(cls, config: EmbedConfig) -> "EmbedChatLook":
        return cls(
            theme=config.theme,
            position=config.position,
            primary_color=config.primary_color,
            assistant_title=config.assistant_title,
            placeholder=config.placeholder,
            interface_locale=config.interface_locale,
            show_launcher=config.show_launcher,
            branding=config.branding,
            voice_enabled=config.voice_enabled,
            voice_default_on=config.voice_default_on,
        )


class EmbedMapping(BaseModel):
    """
    Глобальный маппинг embed_id -> company_id.
    Хранится с префиксом embed_mapping: глобально (is_global=True).

    Необходим для публичного API, который не знает company_id заранее.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "embed_mapping"}
    )

    embed_id: str = Field(
        title="ID виджета",
        description="Публичный идентификатор виджета",
        json_schema_extra={"readonly": True},
    )
    company_id: str = Field(
        title="ID компании",
        description="ID компании, которой принадлежит виджет",
        json_schema_extra={"readonly": True},
    )

