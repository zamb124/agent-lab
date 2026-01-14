"""
Dependency injection для FastAPI endpoints.
"""

from core.context import get_context
from apps.crm.container import CRMContainer, get_crm_container
from apps.crm.services.entity_service import EntityService
from apps.crm.services.access_control_service import AccessControlService
from apps.crm.services.access_grant_service import AccessGrantService
from apps.crm.services.access_request_service import AccessRequestService
from apps.crm.services.graph_service import GraphService

_initialized_companies: set = set()


async def get_container_dep() -> CRMContainer:
    """Получить CRM контейнер для FastAPI dependencies"""
    container = get_crm_container()
    
    context = get_context()
    if context and context.active_company:
        company_id = context.active_company.company_id
        if company_id not in _initialized_companies:
            await container.company_init_service.initialize_company(company_id)
            _initialized_companies.add(company_id)
    
    return container


def get_entity_service() -> EntityService:
    """Получить EntityService из контейнера"""
    container = get_crm_container()
    return container.entity_service


def get_access_control_service() -> AccessControlService:
    """Получить AccessControlService из контейнера"""
    container = get_crm_container()
    return container.access_control_service


def get_access_grant_service() -> AccessGrantService:
    """Получить AccessGrantService из контейнера"""
    container = get_crm_container()
    return container.access_grant_service


def get_access_request_service() -> AccessRequestService:
    """Получить AccessRequestService из контейнера"""
    container = get_crm_container()
    return container.access_request_service


def get_graph_service() -> GraphService:
    """Получить GraphService из контейнера"""
    container = get_crm_container()
    return container.graph_service
