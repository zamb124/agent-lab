"""
API для профиля пользователя.
"""

from typing import Dict, Any, List

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from apps.crm.dependencies import ProfileServiceDep
from apps.crm.models.profile_models import (
    UserProfileCreate,
    UserProfileResponse,
    UserStatsResponse,
    TelegramLinkRequest,
    TelegramLinkResponse,
)

router = APIRouter()


class SidebarConfigUpdate(BaseModel):
    """Обновление настроек sidebar"""
    items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Список элементов меню с настройками видимости и порядка"
    )


class WidgetConfigUpdate(BaseModel):
    """Обновление настроек виджетов"""
    enabled_widgets: List[str] = Field(
        default_factory=list,
        description="Список включенных виджетов"
    )
    layout: Dict[str, Any] = Field(
        default_factory=dict,
        description="Расположение виджетов"
    )


@router.get("", response_model=UserProfileResponse)
async def get_profile(
    service: ProfileServiceDep,
):
    """
    Получает профиль текущего пользователя.
    Если профиль не существует - создает пустой.
    """
    return await service.get_profile()


@router.put("", response_model=UserProfileResponse)
async def update_profile(
    data: UserProfileCreate,
    service: ProfileServiceDep,
):
    """
    Обновляет профиль текущего пользователя.
    """
    return await service.update_profile(data)


@router.get("/stats", response_model=UserStatsResponse)
async def get_stats(
    service: ProfileServiceDep,
    days: int = Query(365, ge=7, le=730, description="Период в днях"),
):
    """
    Получает статистику активности пользователя.
    Используется для графика продуктивности (как на GitHub).
    """
    return await service.get_stats(days)


@router.put("/sidebar", response_model=UserProfileResponse)
async def update_sidebar_config(
    data: SidebarConfigUpdate,
    service: ProfileServiceDep,
):
    """
    Обновляет настройки sidebar меню.
    Позволяет скрывать/показывать элементы и менять порядок.
    """
    return await service.update_profile(
        UserProfileCreate(sidebar_config={"items": data.items})
    )


@router.put("/widgets", response_model=UserProfileResponse)
async def update_widget_config(
    data: WidgetConfigUpdate,
    service: ProfileServiceDep,
):
    """
    Обновляет настройки виджетов на главной.
    Позволяет включать/отключать виджеты.
    """
    return await service.update_profile(
        UserProfileCreate(widget_config={
            "enabled_widgets": data.enabled_widgets,
            "layout": data.layout
        })
    )


@router.get("/sidebar/defaults")
async def get_sidebar_defaults():
    """
    Возвращает дефолтную конфигурацию sidebar.
    Используется для отображения всех доступных элементов.
    """
    return {
        "items": [
            {"id": "dashboard", "label": "Главная", "icon": "home", "visible": True, "order": 0},
            {"id": "notes", "label": "Заметки", "icon": "file-text", "visible": True, "order": 1},
            {"id": "tasks", "label": "Задачи", "icon": "check-square", "visible": True, "order": 2},
            {"id": "entities", "label": "Контакты", "icon": "users", "visible": True, "order": 3},
            {"id": "graph", "label": "Граф связей", "icon": "git-branch", "visible": True, "order": 4},
            {"id": "calendar", "label": "Календарь", "icon": "calendar", "visible": True, "order": 5},
            {"id": "access-requests", "label": "Запросы доступа", "icon": "lock", "visible": True, "order": 6},
            {"id": "profile", "label": "Профиль", "icon": "user", "visible": True, "order": 7},
        ]
    }


@router.post("/telegram/link", response_model=TelegramLinkResponse)
async def link_telegram(
    data: TelegramLinkRequest,
    service: ProfileServiceDep,
):
    """
    Привязывает Telegram username к профилю.
    
    После привязки пользователь сможет использовать CRM через Telegram бота.
    Username указывается без @.
    """
    return await service.link_telegram(data.telegram_username)


@router.delete("/telegram/link", response_model=TelegramLinkResponse)
async def unlink_telegram(
    service: ProfileServiceDep,
):
    """Отвязывает Telegram от профиля"""
    return await service.unlink_telegram()

