"""
CRM Models.
"""

from apps.crm.db.models import CRMEntity
from apps.crm.models.api import (
    AIAnalyzeRequest,
    AIAnalyzeResponse,
    EntityCreate,
    EntityResponse,
    EntityTypeCreate,
    EntityTypeResponse,
    EntityUpdate,
    RelationshipCreate,
    RelationshipResponse,
    RelationshipTypeCreate,
    RelationshipTypeResponse,
)

__all__ = [
    "CRMEntity",
    "EntityCreate",
    "EntityUpdate",
    "EntityResponse",
    "EntityTypeCreate",
    "EntityTypeResponse",
    "RelationshipTypeCreate",
    "RelationshipTypeResponse",
    "RelationshipCreate",
    "RelationshipResponse",
    "AIAnalyzeRequest",
    "AIAnalyzeResponse",
]

