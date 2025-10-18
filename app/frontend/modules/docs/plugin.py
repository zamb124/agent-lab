"""
Docs Plugin - документация
"""

from app.frontend.core.plugin_system import Plugin
from fastapi import APIRouter

router = APIRouter()


class DocsPlugin(Plugin):
    """Плагин документации"""
    
    name = "docs"
    display_name = "Документация"
    version = "1.0.0"
    description = "Техническая документация проекта"
    author = "Agents Lab"
    
    requires_auth = False
    
    static_css = []
    static_js = []
    
    sidebar_items = []
    
    footer_items = [
        {
            "id": "docs",
            "label": "dashboard.navigation.docs",
            "icon": "bi-book",
            "url": "/docs",
            "order": 10,
            "target": "_blank"
        }
    ]
    
    def get_router(self):
        return router

