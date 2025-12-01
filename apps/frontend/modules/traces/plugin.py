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
            "icon": "bi-diagram-3",
            "url": "/frontend/traces/",
            "order": 45,
            "type": "htmx"
        }
    ]

    dashboard_widgets = [
        {
            "id": "traces",
            "title": "dashboard.widgets.traces",
            "description": "Просмотр OpenTelemetry трейсов",
            "icon": "bi-diagram-3",
            "url": "/frontend/traces/",
            "order": 45
        }
    ]

    def get_router(self):
        from .router import router
        return router



