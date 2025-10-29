"""
MCP Plugin - управление MCP серверами
"""

from app.frontend.core.plugin_system import Plugin


class MCPPlugin(Plugin):
    """Плагин для управления MCP (Model Context Protocol) серверами"""
    
    name = "mcp"
    display_name = "MCP Серверы"
    version = "1.0.0"
    description = "Управление MCP серверами и синхронизация инструментов"
    author = "Agents Lab"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["mcp.css"]
    static_js = ["mcp.module.js"]
    
    sidebar_items = [
        {
            "id": "mcp",
            "label": "dashboard.navigation.mcp",
            "icon": "plug",
            "url": "/frontend/mcp/",
            "order": 60,
            "type": "htmx"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "mcp_widget",
            "title": "dashboard.widgets.mcp",
            "description": "Интеграция с внешними MCP серверами",
            "icon": "plug",
            "url": "/frontend/mcp/",
            "order": 60
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

