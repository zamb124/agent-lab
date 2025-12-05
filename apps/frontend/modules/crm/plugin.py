"""
CRM Plugin - Networkle
Standalone модуль для управления контактами и Knowledge Graph
"""

from apps.frontend.core.plugin_system import Plugin


class CRMPlugin(Plugin):
    """Плагин CRM Networkle - standalone приложение"""
    
    name = "crm"
    display_name = "Networkle CRM"
    version = "1.0.0"
    description = "Управление контактами, заметками и Knowledge Graph"
    author = "Humanitec"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["crm.css"]
    static_js = ["crm.module.js"]
    
    # В основном dashboard только виджет со ссылкой на CRM
    sidebar_items = [
        {
            "id": "crm",
            "label": "Networkle CRM",
            "icon": "affiliate",
            "url": "/crm/",
            "order": 85,
            "type": "page"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "crm_widget",
            "title": "Networkle CRM",
            "description": "Контакты, заметки и Knowledge Graph",
            "icon": "affiliate",
            "url": "/crm/",
            "order": 85
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

