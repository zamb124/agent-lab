"""AgentSkill — progressive procedure pack для llm_node (DB-first catalog)."""

from __future__ import annotations

import re
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from apps.flows.src.models.tool_reference import ToolReference
from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.types import JsonObject, parse_json_object

_AGENT_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AgentSkillIndexEntry(StrictBaseModel):
    """Tier-1 index entry for standing llm_node context."""

    agent_skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=1024)


class AgentSkill(StrictBaseModel):
    """Catalog skill: procedure body + optional tools/files/depends_on."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        json_schema_extra={"storage_prefix": "agent_skill"},
        extra="forbid",
    )

    agent_skill_id: str = Field(..., min_length=1, description="Стабильный id (slug)")
    name: str = Field(..., min_length=1, max_length=64, description="agentskills name")
    description: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="Tier-1: what the skill does and when to use it",
    )
    body_markdown: str = Field(..., min_length=1, description="Tier-2 procedure markdown")
    tool_refs: list[ToolReference] = Field(
        default_factory=list,
        description="Tools materialized into llm_node on load_agent_skill",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description=(
            "agent_skill_id children loadable after this skill; "
            "arbitrary depth; cycles allowed; reload idempotent"
        ),
    )
    references: list[FileRef] = Field(
        default_factory=list,
        description="Tier-3 reference docs",
    )
    assets: list[FileRef] = Field(
        default_factory=list,
        description="Templates and other assets",
    )

    @field_validator("agent_skill_id", "name")
    @classmethod
    def validate_slug_name(cls, value: str) -> str:
        normalized = value.strip()
        if not _AGENT_SKILL_NAME_RE.fullmatch(normalized):
            raise ValueError(
                f"agent_skill name/id must be lowercase alphanumeric with single hyphens (got {value!r})"
            )
        return normalized

    @field_validator("description", "body_markdown")
    @classmethod
    def validate_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("field must be non-empty after strip")
        return normalized

    @field_validator("depends_on")
    @classmethod
    def validate_depends_on(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in value:
            item = raw.strip()
            if not item:
                raise ValueError("depends_on entries must be non-empty")
            if not _AGENT_SKILL_NAME_RE.fullmatch(item):
                raise ValueError(f"depends_on id is not a valid slug: {raw!r}")
            if item in seen:
                raise ValueError(f"duplicate depends_on entry: {item}")
            seen.add(item)
            cleaned.append(item)
        return cleaned

    @model_validator(mode="after")
    def reject_self_dependency(self) -> AgentSkill:
        if self.agent_skill_id in self.depends_on:
            raise ValueError("agent_skill cannot depend on itself")
        return self

    def to_index_entry(self) -> AgentSkillIndexEntry:
        return AgentSkillIndexEntry(
            agent_skill_id=self.agent_skill_id,
            name=self.name,
            description=self.description,
        )


class AgentSkillListPayload(StrictBaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AgentSkillIdPayload(StrictBaseModel):
    agent_skill_id: str = Field(min_length=1)


class AgentSkillUpdateRequest(StrictBaseModel):
    name: str
    description: str
    body_markdown: str
    tool_refs: list[ToolReference] = []
    depends_on: list[str] = []
    references: list[FileRef] = []
    assets: list[FileRef] = []


class AgentSkillUpdatePayload(AgentSkillUpdateRequest):
    agent_skill_id: str = Field(min_length=1)


class AgentSkillImportRequest(StrictBaseModel):
    markdown: str
    agent_skill_id: str | None = None
    persist: bool = True


class AgentSkillEnsureSeedResponse(StrictBaseModel):
    seeded: int


class AgentSkillDeletedResponse(StrictBaseModel):
    status: Literal["deleted"]
    agent_skill_id: str


def parse_stored_agent_skill(data: str) -> AgentSkill:
    """Deserialize AgentSkill from storage JSON; drop obsolete `activation` if present."""
    payload: JsonObject = parse_json_object(data, "agent_skill")
    _ = payload.pop("activation", None)
    return AgentSkill.model_validate(payload)


__all__ = [
    "AgentSkill",
    "AgentSkillDeletedResponse",
    "AgentSkillEnsureSeedResponse",
    "AgentSkillIdPayload",
    "AgentSkillImportRequest",
    "AgentSkillIndexEntry",
    "AgentSkillListPayload",
    "AgentSkillUpdatePayload",
    "AgentSkillUpdateRequest",
    "parse_stored_agent_skill",
]
