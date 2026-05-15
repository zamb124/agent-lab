"""
Dependency injection для FastAPI endpoints.
"""

from typing import Annotated

from fastapi import Depends

from apps.crm.container import CRMContainer, get_crm_container
from core.context import get_context

_initialized_companies: set[str] = set()


async def get_container() -> CRMContainer:
    """Получить CRM контейнер для FastAPI dependencies."""
    container = get_crm_container()

    context = get_context()
    if context and context.active_company:
        company_id = context.active_company.company_id
        if company_id not in _initialized_companies:
            await container.company_init_service.initialize_company(company_id)
            _initialized_companies.add(company_id)

    return container


ContainerDep = Annotated[CRMContainer, Depends(get_container)]
