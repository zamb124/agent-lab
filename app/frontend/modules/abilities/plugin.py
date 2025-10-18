"""
Плагин модуля Abilities
"""

from app.frontend.core.plugin_system import Plugin


class AbilitiesPlugin(Plugin):
    """Плагин для отображения способностей (агенты и тулы)"""
    
    name = "abilities"
    display_name = "Способности"
    version = "1.0.0"
    description = "Библиотека доступных агентов и инструментов"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["abilities.css"]
    static_js = ["abilities.module.js"]
    
    sidebar_items = [
        {
            "id": "abilities",
            "label": "dashboard.navigation.abilities",
            "icon": "bi-star",
            "url": "/frontend/abilities/",
            "order": 30,
            "type": "htmx"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "abilities_widget",
            "title": "dashboard.widgets.abilities",
            "description": "Библиотека агентов и инструментов",
            "icon": "bi-star",
            "url": "/frontend/abilities/",
            "order": 25
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

