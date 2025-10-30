"""
Builder Plugin - визуальный редактор flows
"""

from app.frontend.core.plugin_system import Plugin


class BuilderPlugin(Plugin):
    """Плагин для визуального редактора flows"""
    
    name = "builder"
    display_name = "Flow Builder"
    version = "1.0.0"
    description = "Визуальный редактор для создания flows"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["builder.css", "element-selector.css"]
    static_js = ["builder.module.js"]
    
    sidebar_items = [
        {
            "id": "builder",
            "label": "dashboard.navigation.builder",
            "icon": "palette",
            "url": "/frontend/builder/",
            "order": 50,
            "type": "page"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "builder_widget",
            "title": "dashboard.widgets.builder",
            "description": "Визуальный редактор для создания сложных flows",
            "icon": "palette",
            "url": "/frontend/builder/",
            "order": 10
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

