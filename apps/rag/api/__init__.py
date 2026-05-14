"""
API роутеры для RAG Service.
"""

from .documents import router as documents_router
from .namespaces import router as namespaces_router
from .providers import router as providers_router
from .search import router as search_router

__all__ = [
    "providers_router",
    "namespaces_router",
    "documents_router",
    "search_router",
]
