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
            "icon": "bi-people-fill",
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
            "icon": "bi-robot",
            "url": "/frontend/bots/",
            "order": 20
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

