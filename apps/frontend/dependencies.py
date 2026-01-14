"""
FastAPI Dependencies для Frontend сервиса
"""
from typing import Annotated
from fastapi import Depends

from apps.frontend.container import get_frontend_container, FrontendContainer


def get_container() -> FrontendContainer:
    """Dependency для получения контейнера"""
    return get_frontend_container()


ContainerDep = Annotated[FrontendContainer, Depends(get_container)]


