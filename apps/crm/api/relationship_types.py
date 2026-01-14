"""
API для работы с типами relationships.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.db.models import RelationshipType
from apps.crm.container import get_crm_container
from core.context import get_context

router = APIRouter(prefix="/relationship-types", tags=["RelationshipTypes"])


class RelationshipTypeCreate(BaseModel):
    """Создание типа связи"""
    type_id: str
    name: str
    prompt: Optional[str] = None
    is_directed: bool = True


class RelationshipTypeResponse(BaseModel):
    """Ответ с типом связи"""
    type_id: str
    name: str
    prompt: Optional[str] = None
    is_directed: bool


def get_relationship_type_repo() -> RelationshipTypeRepository:
    """Получить репозиторий типов relationships"""
    container = get_crm_container()
    return container.relationship_type_repository


@router.post("", response_model=RelationshipTypeResponse)
async def create_relationship_type(
    data: RelationshipTypeCreate,
    repo: RelationshipTypeRepository = Depends(get_relationship_type_repo)
):
    """Создать новый тип связи"""
    rel_type = RelationshipType(
        type_id=data.type_id,
        name=data.name,
        prompt=data.prompt,
        is_directed=data.is_directed
    )
    
    await repo.create_custom_type(rel_type)
    
    return RelationshipTypeResponse(
        type_id=rel_type.type_id,
        name=rel_type.name,
        prompt=rel_type.prompt,
        is_directed=rel_type.is_directed
    )


@router.get("")
async def list_relationship_types(
    repo: RelationshipTypeRepository = Depends(get_relationship_type_repo)
):
    """Получить все типы relationships для компании"""
    context = get_context()
    company_id = context.active_company.company_id
    
    types = await repo.list_all()
    return {"relationship_types": [{"type_id": rt.type_id, "name": rt.name} for rt in types]}

