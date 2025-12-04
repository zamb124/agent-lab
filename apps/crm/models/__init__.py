"""
CRM Pydantic Models.
"""

from apps.crm.models.entity_models import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    EntitySearchRequest,
    EntitySearchResponse,
)
from apps.crm.models.entity_type_models import (
    EntityTypeCreate,
    EntityTypeUpdate,
    EntityTypeResponse,
)
from apps.crm.models.relationship_models import (
    RelationshipCreate,
    RelationshipResponse,
)
from apps.crm.models.note_models import (
    NoteCreate,
    NoteUpdate,
    NoteResponse,
    NoteAnalyzeRequest,
    NoteAnalyzeResponse,
)
from apps.crm.models.task_models import (
    TaskCreate,
    TaskUpdate,
    TaskResponse,
    TaskPriority,
    TaskStatus,
)

__all__ = [
    # Entities
    "EntityCreate",
    "EntityUpdate",
    "EntityResponse",
    "EntitySearchRequest",
    "EntitySearchResponse",
    # Entity Types
    "EntityTypeCreate",
    "EntityTypeUpdate",
    "EntityTypeResponse",
    # Relationships
    "RelationshipCreate",
    "RelationshipResponse",
    # Notes
    "NoteCreate",
    "NoteUpdate",
    "NoteResponse",
    "NoteAnalyzeRequest",
    "NoteAnalyzeResponse",
    # Tasks
    "TaskCreate",
    "TaskUpdate",
    "TaskResponse",
    "TaskPriority",
    "TaskStatus",
]

