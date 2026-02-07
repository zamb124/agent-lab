"""
CRM Models.
"""

from apps.crm.db.models import CRMEntity
from apps.crm.models.api import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntityTypeCreate,
    EntityTypeResponse,
    RelationshipTypeCreate,
    RelationshipTypeResponse,
    RelationshipCreate,
    RelationshipResponse,
    AIAnalyzeRequest,
    AIAnalyzeResponse,
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

