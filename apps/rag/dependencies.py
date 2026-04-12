"""
FastAPI dependencies для RAG Service.
"""

from typing import Annotated

from fastapi import Depends

from .container import RAGContainer, get_rag_container


def get_container() -> RAGContainer:
    return get_rag_container()


ContainerDep = Annotated[RAGContainer, Depends(get_container)]
