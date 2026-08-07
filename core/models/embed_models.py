"""Models for universal embedded Flow UI surfaces."""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from core.models.flow_interface import (
    EmbedInterfaceOverride,
    compact_embed_interface_override,
)
from core.types import JsonObject, require_json_object


class EmbedStatus(str, Enum):
    """Статус встраиваемого виджета"""
    ACTIVE = "active"
    DISABLED = "disabled"


EmbedPresentation = Literal["drawer", "page"]

DEFAULT_EMBED_INPUT_PLACEHOLDER = "Введите сообщение..."


def resolve_embed_presentation(
    *,
    presentation: EmbedPresentation,
    position: str,
) -> EmbedPresentation:
    """Effective host mount mode; position=fullscreen resolves to page."""
    if presentation == "page":
        return "page"
    if position.strip().lower() == "fullscreen":
        return "page"
    return "drawer"


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
    presentation: EmbedPresentation = Field(
        default="drawer",
        title="Режим поверхности",
        description="drawer — FAB + панель; page — полноэкранный Flow UI document",
    )
    theme: str = Field(
        default="dark",
        title="Тема",
        description="Тема оформления (dark, light, auto)",
    )
    position: str = Field(
        default="bottom-right",
        title="Позиция",
        description="Позиция FAB на странице (bottom-right, bottom-left); для presentation=page игнорируется",
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
        description="Показывать брендинг Linnex",
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
    interface_override: EmbedInterfaceOverride | None = Field(
        default=None,
        title="Переопределение Flow UI для embed",
        description=(
            "Частичный policy/initial-content override; component tree "
            "наследуется от FlowConfig.interface"
        ),
    )

    @field_serializer("interface_override")
    def _serialize_interface_override(
        self,
        value: EmbedInterfaceOverride | None,
    ) -> JsonObject | None:
        compact = compact_embed_interface_override(value)
        return (
            None
            if compact is None
            else require_json_object(
                compact.model_dump(mode="json", exclude_unset=True),
                "EmbedInterfaceOverride",
            )
        )

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

    @model_validator(mode="after")
    def _fullscreen_position_to_page(self) -> "EmbedConfig":
        if self.presentation == "drawer" and self.position.strip().lower() == "fullscreen":
            self.presentation = "page"
            self.position = "bottom-right"
        return self


class EmbedInterfaceLook(BaseModel):
    """
    Look&feel проекция EmbedConfig для interface-profile.

    Только host look; документ и values через profile не доставляются.
    """

    presentation: EmbedPresentation
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
    def from_embed_config(cls, config: EmbedConfig) -> "EmbedInterfaceLook":
        presentation = resolve_embed_presentation(
            presentation=config.presentation,
            position=config.position,
        )
        position = config.position
        if presentation == "page":
            position = "bottom-right"
        elif position.strip().lower() not in ("bottom-right", "bottom-left"):
            position = "bottom-right"
        return cls(
            presentation=presentation,
            theme=config.theme,
            position=position,
            primary_color=config.primary_color,
            assistant_title=config.assistant_title,
            placeholder=config.placeholder,
            interface_locale=config.interface_locale,
            show_launcher=False if presentation == "page" else config.show_launcher,
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
