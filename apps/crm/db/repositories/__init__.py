"""
CRM Repositories - работа с реляционной БД через SQLAlchemy.
"""

from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.namespace_template_repository import NamespaceTemplateRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.db.repositories.relationship_type_repository import RelationshipTypeRepository

__all__ = [
    "EntityRepository",
    "EntityTypeRepository",
    "NamespaceTemplateRepository",
    "RelationshipTypeRepository",
    "RelationshipRepository",
]
