"""FastAPI dependencies для CRM сервиса."""

from typing import Annotated

from fastapi import Depends

from apps.crm.container import CRMContainer, get_crm_container


def get_container() -> CRMContainer:
    return get_crm_container()


ContainerDep = Annotated[CRMContainer, Depends(get_container)]
