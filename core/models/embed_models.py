"""Models for universal embedded Flow UI surfaces."""

from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.flow_ui.document import FlowUIConversationSettings, FlowUIPageId


class EmbedStatus(str, Enum):
    """Статус встраиваемого виджета"""
    ACTIVE = "active"
    DISABLED = "disabled"


EmbedPresentation = Literal["drawer", "page"]
EmbedPosition = Literal["bottom-right", "bottom-left"]

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
    position: EmbedPosition = Field(
        default="bottom-right",
        title="Позиция",
        description="Угол страницы для launcher-кнопки drawer; для presentation=page не используется",
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
    session_share_enabled: bool = Field(
        default=False,
        title="Share сессии из embed",
        description=(
            "Разрешить гостю embed-сессии создавать Flow UI share-ссылку на текущий диалог. "
            "По умолчанию выключено; для публичных демо лендинга включается явно."
        ),
    )
    preview_share_link: bool = Field(
        default=False,
        title="Служебный виджет для одноразовой гостевой ссылки из редактора flow",
        description="Не показывается в списке embed configs консоли; создаётся только через preview-share API.",
    )
    conversation: FlowUIConversationSettings | None = Field(
        default=None,
        title="Настройки беседы для embed",
        description="Полные настройки блока conversation; None — как у flow",
    )
    start_page_id: FlowUIPageId | None = Field(
        default=None,
        title="Стартовая страница для embed",
        description="Страница интерфейса flow, с которой открывается виджет; None — как у flow",
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

class EmbedInterfaceLook(BaseModel):
    """
    Look&feel проекция EmbedConfig для ответа GET .../interface.

    Только host look; документ и values через profile не доставляются.
    """

    presentation: EmbedPresentation
    theme: str
    position: EmbedPosition
    primary_color: str
    assistant_title: str | None
    placeholder: str
    interface_locale: str
    show_launcher: bool
    branding: bool
    voice_enabled: bool
    voice_default_on: bool
    session_share_enabled: bool

    @classmethod
    def from_embed_config(cls, config: EmbedConfig) -> "EmbedInterfaceLook":
        return cls(
            presentation=config.presentation,
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
            session_share_enabled=config.session_share_enabled,
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
