"""
CRM Database - модели и репозитории.

Использует реляционный подход с SQLAlchemy для:
- Эффективной фильтрации по индексам
- JOIN'ов между таблицами
- Агрегаций и сортировки
"""

from apps.crm.db.models import (
    Base,
    EntityType,
    Relationship,
    Note,
    Task,
    CompanyMapping,
)
from apps.crm.db.base import CRMDatabase, BaseCRMRepository, get_crm_db

__all__ = [
    # Models
    "Base",
    "EntityType",
    "Relationship",
    "Note",
    "Task",
    "CompanyMapping",
    # Database
    "CRMDatabase",
    "BaseCRMRepository",
    "get_crm_db",
]
