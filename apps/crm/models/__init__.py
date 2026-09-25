"""
CRM Models.
"""

from apps.crm.models.api import (
    AIAnalyzeRequest,
    AIAnalyzeResponse,
    EntityCreate,
    EntityResponse,
    EntityTypeCreate,
    EntityTypeResponse,
    EntityUpdate,
    RelationshipCreate,
    RelationshipTypeCreate,
)
from apps.crm.models.crm_entity import CRMEntity

__all__ = [
    "CRMEntity",
    "EntityCreate",
    "EntityUpdate",
    "EntityResponse",
    "EntityTypeCreate",
    "EntityTypeResponse",
    "RelationshipTypeCreate",
    "RelationshipCreate",
    "AIAnalyzeRequest",
    "AIAnalyzeResponse",
]

