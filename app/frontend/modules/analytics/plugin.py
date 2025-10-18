"""
Analytics Plugin - аналитика с подменю
"""

from app.frontend.core.plugin_system import Plugin


class AnalyticsPlugin(Plugin):
    """Плагин аналитики с вложенным меню"""
    
    name = "analytics"
    display_name = "Аналитика"
    version = "1.0.0"
    description = "Статистика и отчеты с подразделами"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = []
    static_js = []
    
    sidebar_items = [
        {
            "id": "analytics",
            "label": "Аналитика",
            "icon": "bi-graph-up",
            "type": "submenu",
            "order": 50,
            "children": [
                {
                    "id": "analytics_dashboard",
                    "label": "Дашборд",
                    "icon": "bi-speedometer2",
                    "url": "/frontend/analytics/dashboard",
                    "type": "htmx"
                },
                {
                    "id": "analytics_reports",
                    "label": "Отчеты",
                    "icon": "bi-file-earmark-text",
                    "type": "submenu",
                    "children": [
                        {
                            "id": "reports_daily",
                            "label": "Ежедневные",
                            "icon": "bi-calendar-day",
                            "url": "/frontend/analytics/reports/daily",
                            "type": "htmx"
                        },
                        {
                            "id": "reports_monthly",
                            "label": "Ежемесячные",
                            "icon": "bi-calendar-month",
                            "url": "/frontend/analytics/reports/monthly",
                            "type": "htmx"
                        }
                    ]
                },
                {
                    "id": "analytics_export",
                    "label": "Экспорт данных",
                    "icon": "bi-download",
                    "url": "/frontend/analytics/export",
                    "type": "page"
                }
            ]
        }
    ]
    
    def get_router(self):
        from fastapi import APIRouter
        return APIRouter()

