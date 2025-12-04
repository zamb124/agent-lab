"""
CRM Repositories - работа с реляционной БД через SQLAlchemy.
"""

from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.note_repository import NoteRepository
from apps.crm.db.repositories.task_repository import TaskRepository
from apps.crm.db.repositories.company_mapping_repository import CompanyMappingRepository

__all__ = [
    "EntityTypeRepository",
    "RelationshipRepository",
    "NoteRepository",
    "TaskRepository",
    "CompanyMappingRepository",
]
