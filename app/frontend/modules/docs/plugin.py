"""
Docs Plugin - документация
"""

from app.frontend.core.plugin_system import Plugin


class DocsPlugin(Plugin):
    """Плагин документации"""
    
    name = "docs"
    display_name = "Документация"
    version = "1.0.0"
    description = "Документация системы"
    author = "Agents Lab"
    
    requires_auth = False
    
    static_css = []
    static_js = []
    
    sidebar_items = []
    
    footer_items = [
        {
            "id": "docs",
            "label": "Документация",
            "icon": "bi-book",
            "url": "/docs/",
            "target": "_blank",
            "order": 10
        }
    ]
    
    def get_router(self):
        from fastapi import APIRouter
        return APIRouter()

