"""
RAG Plugin - управление RAG неймспейсами и документами
"""

from apps.frontend.core.plugin_system import Plugin


class RAGPlugin(Plugin):
    """Плагин для управления RAG (Retrieval-Augmented Generation)"""
    
    name = "rag"
    display_name = "RAG"
    version = "1.0.0"
    description = "Управление векторными хранилищами и документами"
    author = "Humanitec"
    
    requires_auth = True
    requires_role = "user"
    
    static_css = ["rag.css"]
    static_js = ["rag.module.js"]
    
    sidebar_items = [
        {
            "id": "rag",
            "label": "RAG",
            "icon": "database",
            "url": "/rag/",
            "order": 90,
            "type": "page"
        }
    ]
    
    dashboard_widgets = [
        {
            "id": "rag_widget",
            "title": "RAG",
            "description": "Управление векторными хранилищами",
            "icon": "database",
            "url": "/rag/",
            "order": 90
        }
    ]
    
    def get_router(self):
        from .router import router
        return router

