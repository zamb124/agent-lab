"""
CRM Database - модели и репозитории.

Использует реляционный подход с SQLAlchemy для:
- Эффективной фильтрации по индексам
- JOIN'ов между таблицами
- Агрегаций и сортировки
"""

from apps.crm.db.base import BaseCRMRepository, CRMDatabase, get_crm_db
from apps.crm.db.models import (
    AccessRequest,
    CompanyMapping,
    CRMSuggest,
    EntityType,
    Relationship,
    RelationshipType,
)
from core.db.models.base import Base

__all__ = [
    # Models
    "Base",
    "EntityType",
    "RelationshipType",
    "Relationship",
    "CompanyMapping",
    "AccessRequest",
    "CRMSuggest",
    # Database
    "CRMDatabase",
    "BaseCRMRepository",
    "get_crm_db",
]
