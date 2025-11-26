"""
Chats Plugin - список чатов
"""

from apps.frontend.core.plugin_system import Plugin


class ChatsPlugin(Plugin):
    """Плагин списка чатов"""
    
    name = "chats"
    display_name = "Чаты"
    version = "1.0.0"
    description = "Список активных чатов"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = []
    static_js = []
    
    sidebar_items = [
        {
            "id": "chats",
            "label": "dashboard.navigation.chats",
            "icon": "message",
            "url": "/frontend/chats/",
            "order": 20,
            "type": "htmx",
            "group": "Агенты и Боты",
            "group_icon": "users",
            "group_order": 10
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "chats_widget",
            "title": "dashboard.widgets.chats",
            "description": "Диалоги с пользователями",
            "icon": "message",
            "url": "/frontend/chats/",
            "order": 35
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

