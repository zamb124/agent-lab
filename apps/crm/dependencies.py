"""
FastAPI Dependencies для CRM сервиса.
"""

from typing import Annotated

from fastapi import Depends

from apps.crm.container import get_crm_container, CRMContainer
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.note_repository import NoteRepository
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.db.repositories.company_mapping_repository import CompanyMappingRepository
from apps.crm.services.entity_service import EntityService
from apps.crm.services.entity_type_service import EntityTypeService
from apps.crm.services.relationship_service import RelationshipService
from apps.crm.services.note_service import NoteService
from apps.crm.services.task_service import TaskService
from apps.crm.services.graph_service import GraphService


# === Container ===

def get_container() -> CRMContainer:
    return get_crm_container()


ContainerDep = Annotated[CRMContainer, Depends(get_container)]


# === Repositories ===

def get_entity_type_repository(container: ContainerDep) -> EntityTypeRepository:
    return container.entity_type_repository


def get_relationship_repository(container: ContainerDep) -> RelationshipRepository:
    return container.relationship_repository


def get_note_repository(container: ContainerDep) -> NoteRepository:
    return container.note_repository


def get_task_repository(container: ContainerDep) -> TaskRepository:
    return container.task_repository


def get_company_mapping_repository(container: ContainerDep) -> CompanyMappingRepository:
    return container.company_mapping_repository


EntityTypeRepositoryDep = Annotated[EntityTypeRepository, Depends(get_entity_type_repository)]
RelationshipRepositoryDep = Annotated[RelationshipRepository, Depends(get_relationship_repository)]
NoteRepositoryDep = Annotated[NoteRepository, Depends(get_note_repository)]
TaskRepositoryDep = Annotated[TaskRepository, Depends(get_task_repository)]
CompanyMappingRepositoryDep = Annotated[CompanyMappingRepository, Depends(get_company_mapping_repository)]


# === Services ===

def get_entity_service(container: ContainerDep) -> EntityService:
    return container.entity_service


def get_entity_type_service(container: ContainerDep) -> EntityTypeService:
    return container.entity_type_service


def get_relationship_service(container: ContainerDep) -> RelationshipService:
    return container.relationship_service


def get_note_service(container: ContainerDep) -> NoteService:
    return container.note_service


def get_task_service(container: ContainerDep) -> TaskService:
    return container.task_service


def get_graph_service(container: ContainerDep) -> GraphService:
    return container.graph_service


EntityServiceDep = Annotated[EntityService, Depends(get_entity_service)]
EntityTypeServiceDep = Annotated[EntityTypeService, Depends(get_entity_type_service)]
RelationshipServiceDep = Annotated[RelationshipService, Depends(get_relationship_service)]
NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]

