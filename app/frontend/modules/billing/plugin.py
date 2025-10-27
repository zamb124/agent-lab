"""
Billing Plugin - биллинг и оплата
"""

from app.frontend.core.plugin_system import Plugin


class BillingPlugin(Plugin):
    """Плагин биллинга"""
    
    name = "billing"
    display_name = "Биллинг"
    version = "1.0.0"
    description = "Управление подписками и оплатой"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["billing.css"]
    static_js = ["billing.module.js"]
    
    sidebar_items = []
    
    dashboard_widgets = [
        {
            "id": "billing_widget",
            "title": "dashboard.widgets.billing",
            "description": "Тарифы и оплата",
            "icon": "bi-credit-card",
            "url": "/frontend/billing/",
            "order": 50
        }
    ]
    
    footer_items = [
        {
            "id": "billing",
            "label": "dashboard.navigation.billing",
            "icon": "bi-credit-card",
            "url": "/frontend/billing/",
            "order": 20
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

