"""
Chat Plugin - виджет чата
"""

from apps.frontend.core.plugin_system import Plugin


class ChatPlugin(Plugin):
    """Плагин виджета чата"""
    
    name = "chat"
    display_name = "Чат"
    version = "1.0.0"
    description = "Виджет чата доступен на всех страницах"
    author = "Humanitec"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["chat-widget.css"]
    
    sidebar_items = []
    
    def get_router(self):
        from .router import router
        return router

