"""FastAPI dependencies для Office сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.office.container import OfficeContainer, get_office_container


def get_container() -> OfficeContainer:
    return get_office_container()


ContainerDep = Annotated[OfficeContainer, Depends(get_container)]
