"""
Bots Plugin - управление ботами
"""

from app.frontend.core.plugin_system import Plugin


class BotsPlugin(Plugin):
    """Плагин для управления ботами"""
    
    name = "bots"
    display_name = "Боты"
    version = "1.0.0"
    description = "Управление ботами и агентами"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["bots.css"]
    static_js = ["bots.module.js"]
    
    sidebar_items = [
        {
            "id": "bots",
            "label": "dashboard.navigation.bots",
            "icon": "users",
            "url": "/frontend/bots/",
            "order": 10,
            "type": "htmx"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "bots_widget",
            "title": "dashboard.widgets.bots",
            "description": "Управление ботами и агентами",
            "icon": "robot",
            "url": "/frontend/bots/",
            "order": 20
        }
    ]
    
    header_actions = [
        {
            "id": "bots_save",
            "label": "Сохранить",
            "icon": "device-floppy",
            "action": "bots:save",
            "urls": [
                "/frontend/bots/*/details"
            ],
            "tooltip": "Сохранить изменения бота",
            "order": 5
        },
        {
            "id": "bots_copy_id",
            "label": "Копировать ID",
            "icon": "copy",
            "action": "bots:copy_id",
            "urls": [
                "/frontend/bots/*/details"
            ],
            "tooltip": "Скопировать ID бота",
            "order": 7
        },
        {
            "id": "bots_delete",
            "label": "Удалить",
            "icon": "trash",
            "action": "bots:delete",
            "urls": [
                "/frontend/bots/*/details"
            ],
            "tooltip": "Удалить бота",
            "order": 6
        },
        {
            "id": "bots_create",
            "label": "Создать бота",
            "icon": "plus",
            "action": "bots:create",
            "urls": [
                "/frontend/bots/",
                "/frontend/bots"
            ],
            "tooltip": "Создать нового бота",
            "order": 10
        },
        {
            "id": "bots_refresh",
            "label": "Обновить",
            "icon": "rotate-clockwise",
            "action": "bots:refresh",
            "urls": [
                "/frontend/bots/",
                "/frontend/bots"
            ],
            "tooltip": "Обновить список ботов",
            "order": 8
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

