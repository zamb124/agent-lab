"""
FastAPI dependencies для RAG Service.
"""

from fastapi import Depends

from .container import RAGContainer, get_rag_container


def get_container_dep() -> RAGContainer:
    """Dependency для получения контейнера"""
    return get_rag_container()


