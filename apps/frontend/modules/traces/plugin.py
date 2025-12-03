"""
Traces Plugin - просмотр OpenTelemetry трейсов
"""

from apps.frontend.core.plugin_system import Plugin


class TracesPlugin(Plugin):
    """Плагин для просмотра трейсов"""

    name = "traces"
    display_name = "Трейсы"
    version = "1.0.0"
    description = "Просмотр OpenTelemetry трейсов и spans"
    author = "Humanitec"

    requires_auth = True
    requires_role = "user"

    static_css = ["traces.css"]
    static_js = ["traces.module.js"]

    sidebar_items = [
        {
            "id": "traces",
            "label": "dashboard.navigation.traces",
            "icon": "activity",
            "url": "/frontend/traces/",
            "order": 70,
            "type": "htmx",
            "group": "Инструменты",
            "group_icon": "tools",
            "group_order": 50
        }
    ]

    dashboard_widgets = [
        {
            "id": "traces",
            "title": "dashboard.widgets.traces",
            "description": "Просмотр OpenTelemetry трейсов",
            "icon": "activity",
            "url": "/frontend/traces/",
            "order": 70
        }
    ]

    def get_router(self):
        from .router import router
        return router



