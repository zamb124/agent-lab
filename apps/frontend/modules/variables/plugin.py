"""
Variables Plugin - переменные и ключи
"""

from apps.frontend.core.plugin_system import Plugin


class VariablesPlugin(Plugin):
    """Плагин управления переменными"""
    
    name = "variables"
    display_name = "Переменные"
    version = "1.0.0"
    description = "Управление ключами и переменными"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["variables.css"]
    static_js = ["variables.module.js"]
    
    sidebar_items = [
        {
            "id": "variables",
            "label": "Ключи и Переменные",
            "icon": "key",
            "url": "/frontend/variables/",
            "order": 60,
            "type": "htmx",
            "group": "Инструменты",
            "group_icon": "tools",
            "group_order": 50
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "variables_widget",
            "title": "dashboard.widgets.variables",
            "description": "Ключи и переменные",
            "icon": "key",
            "url": "/frontend/variables/",
            "order": 45
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

