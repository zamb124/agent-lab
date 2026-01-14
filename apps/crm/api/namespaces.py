"""
API для управления namespaces в CRM.
Позволяет создавать изолированные области данных внутри компании.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.logging import get_logger
from core.context import get_context
from core.models.identity_models import Namespace
from apps.crm.container import CRMContainer
from apps.crm.dependencies import get_container_dep

logger = get_logger(__name__)

router = APIRouter(prefix="/namespaces", tags=["CRM Namespaces"])


class NamespaceCreateRequest(BaseModel):
    name: str = Field(..., description="Имя namespace")
    description: str = Field(None, description="Описание namespace")


class NamespaceResponse(BaseModel):
    name: str
    company_id: str
    description: str = None
    is_default: bool = False


class NamespaceListResponse(BaseModel):
    namespaces: List[NamespaceResponse]
    company_id: str


@router.get("", response_model=NamespaceListResponse)
async def list_namespaces(
    container: CRMContainer = Depends(get_container_dep)
) -> NamespaceListResponse:
    """
    Список всех namespaces текущей компании.
    Если пусто - автоматически создается default.
    """
    context = get_context()
    company_id = context.active_company.company_id
    
    namespace_repo = container.namespace_repository
    namespaces = await namespace_repo.list_all()
    
    return NamespaceListResponse(
        namespaces=[
            NamespaceResponse(
                name=ns.name,
                company_id=ns.company_id,
                description=ns.description,
                is_default=ns.is_default
            )
            for ns in namespaces
        ],
        company_id=company_id
    )


@router.post("", status_code=201, response_model=NamespaceResponse)
async def create_namespace(
    request: NamespaceCreateRequest,
    container: CRMContainer = Depends(get_container_dep)
) -> NamespaceResponse:
    """
    Создает новый namespace для текущей компании.
    """
    context = get_context()
    company_id = context.active_company.company_id
    
    namespace_repo = container.namespace_repository
    
    existing = await namespace_repo.get(request.name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Namespace {request.name} already exists"
        )
    
    namespace = Namespace(
        name=request.name,
        company_id=company_id,
        description=request.description,
        is_default=False
    )
    
    await namespace_repo.set(namespace)
    
    logger.info(f"Создан namespace {request.name} для компании {company_id}")
    
    return NamespaceResponse(
        name=namespace.name,
        company_id=namespace.company_id,
        description=namespace.description,
        is_default=namespace.is_default
    )
