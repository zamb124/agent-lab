"""
Модели для системы встраиваемых виджетов чата.
"""

from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class EmbedStatus(str, Enum):
    """Статус встраиваемого виджета"""
    ACTIVE = "active"
    DISABLED = "disabled"


class EmbedConfig(BaseModel):
    """
    Конфигурация встраиваемого виджета чата.
    Хранится с префиксом embed_config: в storage компании.
    
    is_global=False - изоляция по компаниям через префикс company:{company_id}:
    """
    
    model_config = ConfigDict(
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
    allowed_origins: List[str] = Field(
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
    show_reasoning: bool = Field(
        default=False,
        title="Показывать reasoning",
        description="Показывать процесс рассуждения агента",
    )
    show_tool_calls: bool = Field(
        default=False,
        title="Показывать tool calls",
        description="Показывать вызовы инструментов",
    )
    primary_color: str = Field(
        default="#6366f1",
        title="Основной цвет",
        description="Основной цвет интерфейса (HEX)",
    )
    greeting_message: Optional[str] = Field(
        default=None,
        title="Приветствие",
        description="Приветственное сообщение при загрузке чата",
    )
    assistant_title: Optional[str] = Field(
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
        default="Введите сообщение...",
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
    landing_card_image_url: Optional[str] = Field(
        default=None,
        title="Картинка карточки на лендинге",
        description="URL изображения для карточки демо-сотрудника (обязателен при landing_visible)",
    )
    landing_sort_order: int = Field(
        default=0,
        title="Порядок в каталоге лендинга",
        description="Меньше — выше в списке",
    )
    
    # Статистика
    usage_count: int = Field(
        default=0,
        title="Количество использований",
        description="Счетчик использований виджета",
        json_schema_extra={"readonly": True},
    )
    last_used_at: Optional[datetime] = Field(
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


class EmbedMapping(BaseModel):
    """
    Глобальный маппинг embed_id -> company_id.
    Хранится с префиксом embed_mapping: глобально (is_global=True).
    
    Необходим для публичного API, который не знает company_id заранее.
    """
    
    model_config = ConfigDict(
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


