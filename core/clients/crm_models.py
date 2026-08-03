"""Pydantic input models for CRM REST client and Flows tools."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from core.types import JsonObject, JsonValue


class CrmSearchEntitiesArgs(BaseModel):
    """Args for POST /crm/api/v1/entities/query — same semantics as CRM UI search."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("query", "search"),
        description=(
            "Semantic search text (vector over name/description), like the entity list search box. "
            "Call argument name is query."
        ),
    )
    entity_type: str | None = Field(
        None,
        description="Only when the user explicitly limited entity type; otherwise null.",
    )
    entity_subtype: str | None = Field(
        None,
        description="Only when the user asked for a subtype; otherwise null.",
    )
    namespace: str | None = Field(
        None,
        description="Namespace; null — active_namespace from session. Do not invent default.",
    )
    limit: int = Field(100, ge=1, le=1000, description="Max results (UI often uses 100).")

    @field_validator("entity_type", "entity_subtype", "namespace", mode="before")
    @classmethod
    def _optional_str(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrmCapabilityCreateNoteArgs(BaseModel):
    """Create note without Lara propose/apply (eval / code_node / CrmClient.create_note)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, description="Note title.")
    description: str = Field(..., min_length=1, description="Note body.")
    note_date: str | None = Field(None, description="YYYY-MM-DD; optional.")
    namespace: str | None = Field(None, description="Namespace; null — from context.")


class CrmCreateNoteArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    mode: Literal["propose", "apply"] = Field(
        "propose",
        description="propose — prepare create for confirmation; apply — execute by pending_action_id.",
    )
    name: str | None = Field(None, description="Note title (required for mode=propose).")
    description: str | None = Field(None, description="Note body (required for mode=propose).")
    note_date: str | None = Field(
        None,
        description="Note date YYYY-MM-DD when meaningful.",
    )
    namespace: str | None = Field(
        None,
        description="CRM namespace; null — from session context.",
    )
    pending_action_id: str | None = Field(
        None,
        description="Action id from propose. Required for mode=apply.",
    )
    idempotency_key: str | None = Field(
        None,
        description="Idempotency key; defaults to pending_action_id when omitted.",
    )

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            return v.strip() or None
        return v

    @field_validator("description", mode="before")
    @classmethod
    def _strip_description(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            return s if s else None
        return v

    @model_validator(mode="after")
    def _mode_requirements(self) -> CrmCreateNoteArgs:
        if self.mode == "apply":
            if self.pending_action_id is None or not str(self.pending_action_id).strip():
                raise ValueError("pending_action_id is required when mode='apply'")
            return self
        if self.name is None:
            raise ValueError("name is required when mode='propose'")
        if self.description is None:
            raise ValueError("description is required when mode='propose'")
        return self

    @field_validator("note_date", "namespace", "pending_action_id", mode="before")
    @classmethod
    def _optional_str_note(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrmAnalyzeNoteTextArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    note_id: str = Field(..., min_length=1, description="entity_id of the note to analyze.")
    extract_entity_types: list[str] | None = Field(
        None,
        description="Limit extraction to these entity types; omit otherwise.",
    )
    mentioned_entity_ids: list[str] | None = Field(
        None,
        description="Known entity ids for analysis context; optional.",
    )

    @field_validator("note_id", mode="before")
    @classmethod
    def _strip_note_id(cls, v: JsonValue) -> JsonValue:
        if isinstance(v, str):
            return v.strip() or None
        return v


class CrmCreateNoteAndAnalyzeArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="Title of the new note.")
    description: str = Field(
        ...,
        min_length=1,
        description="Note body; the same text is analyzed.",
    )
    note_date: str | None = Field(None, description="Date YYYY-MM-DD; optional.")
    extract_entity_types: list[str] | None = Field(
        None,
        description="Entity types to extract during analysis; optional.",
    )
    mentioned_entity_ids: list[str] | None = Field(
        None,
        description="Mentioned entity ids for analysis context; optional.",
    )
    namespace: str | None = Field(None, description="Namespace; null — from context.")

    @field_validator("note_date", "namespace", mode="before")
    @classmethod
    def _optional_str_combo(cls, v: JsonValue) -> JsonValue:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


class CrmGetEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(..., min_length=1, description="entity_id CRM.")


class CrmCreateEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_type: str = Field(..., min_length=1, description="Entity type_id from catalog.")
    name: str = Field(..., min_length=1, description="Display name.")
    entity_subtype: str | None = Field(None, description="Optional subtype.")
    namespace: str | None = Field(None, description="Namespace; null — active_namespace.")
    description: str | None = Field(None, description="Optional description.")
    attributes: JsonObject | None = Field(None, description="Custom attributes object.")
    tags: list[str] | None = Field(None, description="Optional tags.")


class CrmCreateRelationshipArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_entity_id: str = Field(..., min_length=1, description="Source entity_id.")
    target_entity_id: str = Field(..., min_length=1, description="Target entity_id.")
    relationship_type: str = Field(..., min_length=1, description="relationship_type type_id.")
    namespace: str | None = Field(None, description="Namespace; null — active_namespace.")
    weight: float = Field(default=1.0, ge=0.0, description="Edge weight.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Edge confidence 0..1.")


class CrmListEntityTypesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(None, description="Namespace; null — active_namespace.")


class CrmDailySummaryArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date: str = Field(..., min_length=10, max_length=10, description="YYYY-MM-DD.")
    namespace: str | None = Field(None, description="Namespace; null — session.")
    force_rebuild: bool = Field(False, description="Force rebuild of cached summary.")


class CrmUpdateEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(..., min_length=1, description="entity_id from search/get. Never invent.")
    name: str | None = Field(default=None, description="New display name; omit to keep.")
    description: str | None = Field(default=None, description="New description; omit to keep.")
    status: str | None = Field(default=None, description="Entity status; omit to keep.")
    entity_type: str | None = Field(default=None, description="Change type only if user asked.")
    entity_subtype: str | None = Field(default=None, description="Change subtype only if user asked.")
    tags: list[str] | None = Field(default=None, description="Replace tags list when provided.")
    note_date: str | None = Field(
        default=None,
        description="For notes: YYYY-MM-DD note_date; omit to keep.",
    )


class CrmDeleteEntityArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(
        ...,
        min_length=1,
        description="entity_id to cascade-delete. Confirm with the user first. Never invent.",
    )


class CrmListNotesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date_from: str = Field(
        ...,
        min_length=10,
        max_length=10,
        description="Inclusive note_date start YYYY-MM-DD.",
    )
    date_to: str | None = Field(
        default=None,
        description="Inclusive note_date end YYYY-MM-DD; omit — same as date_from.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace from session.",
    )
    query: str | None = Field(
        default=None,
        description="Optional text/semantic query over notes; omit for pure date listing.",
    )
    limit: int = Field(default=50, ge=1, le=1000, description="Page size.")
    cursor: str | None = Field(default=None, description="Opaque next_cursor.")


class CrmApplyAnalysisDraftArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note_id: str = Field(
        ...,
        min_length=1,
        description="note_id / entity_id of the note with ai_analysis_draft. Never invent.",
    )


class CrmDiscardAnalysisDraftArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note_id: str = Field(
        ...,
        min_length=1,
        description="note_id whose analysis draft to discard. Never invent.",
    )


class CrmMergeEntitiesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    survivor_entity_id: str = Field(
        ...,
        min_length=1,
        description="entity_id that remains after merge.",
    )
    source_entity_id: str = Field(
        ...,
        min_length=1,
        description="entity_id that is merged into survivor and deleted.",
    )


class CrmPeriodSummaryArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    date_from: str = Field(..., min_length=10, max_length=10, description="Period start YYYY-MM-DD.")
    date_to: str = Field(..., min_length=10, max_length=10, description="Period end YYYY-MM-DD.")
    namespace: str | None = Field(default=None, description="Namespace; null — session.")
    force_rebuild: bool = Field(False, description="Force rebuild of cached summary.")


class CrmCreateActivityTaskArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, description="Task title (CRM entity name).")
    description: str | None = Field(default=None, description="Optional task description.")
    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace.",
    )
    entity_subtype: str | None = Field(default=None, description="Optional task subtype.")
    priority: str | None = Field(
        default=None,
        description="WorkItem priority (low/normal/high/urgent) when creating the pair.",
    )
    due_date: str | None = Field(default=None, description="Optional due_date YYYY-MM-DD.")
    assignees: list[str] | None = Field(
        default=None,
        description="user_id assignees from team_resolve_user / team_list_members. Never invent.",
    )
    tags: list[str] | None = Field(default=None, description="Optional tags.")


class CrmListActivityTasksArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(default=None, description="Namespace filter; null — all company.")
    work_item_state: str | None = Field(
        default=None,
        description="WorkItemState filter: open/in_progress/blocked/done/cancelled/failed.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Page size.")
    offset: int = Field(default=0, ge=0, description="Offset for offset pagination.")


class CrmListRelationshipsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str | None = Field(
        default=None,
        description="Filter edges where entity is source or target. Prefer when browsing one node.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace filter; null — active_namespace from session.",
    )
    limit: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Page size when listing company-wide.",
    )
    cursor: str | None = Field(default=None, description="Opaque next_cursor from previous page.")


class CrmDeleteRelationshipArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    relationship_id: str = Field(
        ...,
        min_length=1,
        description="relationship_id from crm_list_relationships / create. Never invent.",
    )


class CrmListRelationshipTypesArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    limit: int = Field(default=200, ge=1, le=1000, description="Page size.")
    offset: int = Field(default=0, ge=0, description="Offset.")


class CrmEntityRelatedArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    entity_id: str = Field(..., min_length=1, description="Center entity_id. Never invent.")
    direction: Literal["incoming", "outgoing", "both"] = Field(
        default="both",
        description="Edge direction filter.",
    )
    relationship_type: str | None = Field(
        default=None,
        description="Optional relationship_type type_id filter.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace for traversal filter; null — active_namespace.",
    )


class CrmShortestPathArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    from_entity_id: str = Field(..., min_length=1, description="Start entity_id.")
    to_entity_id: str = Field(..., min_length=1, description="End entity_id.")
    max_depth: int = Field(default=10, ge=1, le=20, description="Max path depth.")
    namespace: str | None = Field(
        default=None,
        description="Namespace for traversal; null — active_namespace.",
    )


class CrmListSuggestsArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace from session.",
    )
    status: str = Field(
        default="pending",
        description="Suggest status filter (default pending).",
    )
    limit: int = Field(default=50, ge=1, le=100, description="Page size.")
    offset: int = Field(default=0, ge=0, description="Offset.")


class CrmSuggestIdArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    suggest_id: str = Field(
        ...,
        min_length=1,
        description="suggest_id from crm_list_suggests. Never invent.",
    )
    namespace: str | None = Field(
        default=None,
        description="Namespace; null — active_namespace.",
    )


class CrmKnowledgeImportStatusArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    namespace: str | None = Field(
        default=None,
        description="Namespace filter; null — active_namespace.",
    )
    limit: int = Field(default=50, ge=1, le=200, description="Page size.")
    offset: int = Field(default=0, ge=0, description="Offset.")


__all__ = [
    "CrmSearchEntitiesArgs",
    "CrmCapabilityCreateNoteArgs",
    "CrmCreateNoteArgs",
    "CrmAnalyzeNoteTextArgs",
    "CrmCreateNoteAndAnalyzeArgs",
    "CrmGetEntityArgs",
    "CrmCreateEntityArgs",
    "CrmCreateRelationshipArgs",
    "CrmListEntityTypesArgs",
    "CrmDailySummaryArgs",
    "CrmUpdateEntityArgs",
    "CrmDeleteEntityArgs",
    "CrmListNotesArgs",
    "CrmApplyAnalysisDraftArgs",
    "CrmDiscardAnalysisDraftArgs",
    "CrmMergeEntitiesArgs",
    "CrmPeriodSummaryArgs",
    "CrmCreateActivityTaskArgs",
    "CrmListActivityTasksArgs",
    "CrmListRelationshipsArgs",
    "CrmDeleteRelationshipArgs",
    "CrmListRelationshipTypesArgs",
    "CrmEntityRelatedArgs",
    "CrmShortestPathArgs",
    "CrmListSuggestsArgs",
    "CrmSuggestIdArgs",
    "CrmKnowledgeImportStatusArgs",
]
