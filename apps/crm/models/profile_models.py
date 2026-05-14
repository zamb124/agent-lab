"""
Pydantic модели для профиля пользователя CRM.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SidebarItemConfig(BaseModel):
    """Конфигурация элемента sidebar"""
    id: str = Field(title="ID элемента")
    visible: bool = Field(default=True, title="Видимость")
    order: int = Field(default=0, title="Порядок отображения")


class SidebarConfig(BaseModel):
    """Конфигурация sidebar"""
    items: List[SidebarItemConfig] = Field(default_factory=list, title="Элементы меню")


class WidgetConfig(BaseModel):
    """Конфигурация виджетов на главной"""
    enabled_widgets: List[str] = Field(
        default_factory=lambda: ["tasks", "notes", "calendar"],
        title="Включенные виджеты"
    )
    layout: Dict[str, Any] = Field(default_factory=dict, title="Расположение виджетов")


class TelegramLinkRequest(BaseModel):
    """Запрос на привязку Telegram аккаунта"""
    telegram_username: str = Field(title="Username в Telegram (без @)")


class TelegramLinkResponse(BaseModel):
    """Ответ о привязке Telegram"""
    linked: bool = Field(title="Успешно привязан")
    telegram_username: Optional[str] = Field(default=None)


class UserProfileCreate(BaseModel):
    """Создание/обновление профиля"""

    model_config = ConfigDict(from_attributes=True)

    user_id: Optional[str] = Field(
        default=None,
        max_length=100,
        title="ID пользователя"
    )
    display_name: Optional[str] = Field(
        default=None,
        max_length=100,
        title="Отображаемое имя"
    )
    position: Optional[str] = Field(
        default=None,
        max_length=100,
        title="Должность"
    )
    avatar_url: Optional[str] = Field(
        default=None,
        max_length=500,
        title="URL аватара"
    )
    phone: Optional[str] = Field(
        default=None,
        max_length=50,
        title="Телефон"
    )
    bio: Optional[str] = Field(
        default=None,
        max_length=500,
        title="О себе"
    )
    telegram_username: Optional[str] = Field(
        default=None,
        max_length=100,
        title="Telegram username"
    )
    sidebar_config: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Настройки sidebar"
    )
    widget_config: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Настройки виджетов"
    )


class UserProfileResponse(BaseModel):
    """Ответ с данными профиля"""

    model_config = ConfigDict(from_attributes=True)

    profile_id: str = Field(title="ID профиля")
    user_id: str = Field(title="ID пользователя")
    company_id: str = Field(title="ID компании")
    display_name: Optional[str] = Field(default=None, title="Отображаемое имя")
    position: Optional[str] = Field(default=None, title="Должность")
    avatar_url: Optional[str] = Field(default=None, title="URL аватара")
    phone: Optional[str] = Field(default=None, title="Телефон")
    bio: Optional[str] = Field(default=None, title="О себе")
    telegram_username: Optional[str] = Field(default=None, title="Telegram Username")
    sidebar_config: Dict[str, Any] = Field(default_factory=dict, title="Настройки sidebar")
    widget_config: Dict[str, Any] = Field(default_factory=dict, title="Настройки виджетов")
    created_at: datetime = Field(title="Дата создания")
    updated_at: datetime = Field(title="Дата обновления")

    # Статистика
    notes_count: int = Field(default=0, title="Количество заметок")
    tasks_completed: int = Field(default=0, title="Завершенных задач")
    entities_created: int = Field(default=0, title="Созданных сущностей")


class UserStatsResponse(BaseModel):
    """Статистика пользователя для графика продуктивности"""

    model_config = ConfigDict(from_attributes=True)

    notes_by_date: dict = Field(default_factory=dict, title="Заметки по датам")
    tasks_by_date: dict = Field(default_factory=dict, title="Задачи по датам")
    total_notes: int = Field(default=0)
    total_tasks_completed: int = Field(default=0)
    current_streak: int = Field(default=0, title="Текущая серия дней")
    longest_streak: int = Field(default=0, title="Максимальная серия")

