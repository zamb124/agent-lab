"""
CRM Repositories - работа с реляционной БД через SQLAlchemy.
"""

from apps.crm.db.repositories.entity_repository import EntityChromaRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository

__all__ = [
    "EntityChromaRepository",
    "EntityTypeRepository",
    "RelationshipTypeRepository",
    "RelationshipRepository",
]
