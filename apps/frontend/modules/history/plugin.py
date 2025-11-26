"""
History Plugin - история сессий
"""

from apps.frontend.core.plugin_system import Plugin


class HistoryPlugin(Plugin):
    """Плагин истории диалогов"""
    
    name = "history"
    display_name = "История"
    version = "1.0.0"
    description = "История диалогов и сессий"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["history.css"]
    static_js = []
    
    sidebar_items = [
        {
            "id": "history",
            "label": "dashboard.navigation.history",
            "icon": "history",
            "url": "/frontend/history/",
            "order": 40,
            "type": "htmx",
            "group": "Агенты и Боты",
            "group_icon": "history",
            "group_order": 40
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "history",
            "title": "dashboard.widgets.history",
            "description": "История диалогов и сессий",
            "icon": "history",
            "url": "/frontend/history/",
            "order": 40
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

