"""
Store Plugin - магазин готовых решений
"""

from app.frontend.core.plugin_system import Plugin


class StorePlugin(Plugin):
    """Плагин магазина готовых решений"""
    
    name = "store"
    display_name = "Магазин"
    version = "1.0.0"
    description = "Магазин готовых ботов и flows"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["store.css"]
    static_js = ["store.module.js"]
    
    sidebar_items = [
        {
            "id": "store",
            "label": "dashboard.navigation.store",
            "icon": "bi-shop",
            "url": "/frontend/store/",
            "order": 30,
            "type": "htmx"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "store_widget",
            "title": "Магазин",
            "description": "Готовые решения и шаблоны",
            "icon": "bi-shop",
            "url": "/frontend/store/",
            "order": 30
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

