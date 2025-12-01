"""
Store Plugin - магазин готовых решений
"""

from apps.frontend.core.plugin_system import Plugin


class StorePlugin(Plugin):
    """Плагин магазина готовых решений"""
    
    name = "store"
    display_name = "Магазин"
    version = "1.0.0"
    description = "Магазин готовых ботов и flows"
    author = "Humanitec"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["store.css"]
    static_js = ["store.module.js"]
    
    sidebar_items = [
        {
            "id": "store",
            "label": "dashboard.navigation.store",
            "icon": "shopping-cart",
            "url": "/frontend/store/",
            "order": 30,
            "type": "htmx"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "store_widget",
            "title": "dashboard.widgets.store",
            "description": "Готовые решения и шаблоны",
            "icon": "shopping-cart",
            "url": "/frontend/store/",
            "order": 30
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

