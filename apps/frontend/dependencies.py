"""FastAPI dependencies для Frontend сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.frontend.container import FrontendContainer, get_frontend_container


def get_container() -> FrontendContainer:
    return get_frontend_container()


ContainerDep = Annotated[FrontendContainer, Depends(get_container)]
