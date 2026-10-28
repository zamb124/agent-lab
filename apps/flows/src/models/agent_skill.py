"""AgentSkill — progressive procedure pack для llm_node (DB-first catalog)."""

from __future__ import annotations

import re
from typing import ClassVar, Literal, Self, override

from oxyde import Field as DbField
from pydantic import ConfigDict, Field, ValidationError, field_validator, model_validator

from apps.flows.src.models.enums import CodeMode
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.tools.builtin_specs import builtin_tool_ids
from core.context.context import require_active_company
from core.files.file_ref import FileRef
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject, JsonValue, parse_yaml_value, require_json_object

logger = get_logger(__name__)

_AGENT_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)
_EMPTY_OBJECT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


class AgentSkillIndexEntry(StrictBaseModel):
    """Tier-1 index entry for standing llm_node context."""

    agent_skill_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=1024)


class AgentSkill(CompanyScopedModel):
    """Catalog skill. Таблица ``agent_skills`` в базе flows."""

    __database_alias__: ClassVar[str | None] = "flows"

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    class Meta:
        is_table: bool = True
        table_name: str = "agent_skills"
        unique_together: list[tuple[str, str]] = [("company_id", "agent_skill_id")]

    agent_skill_id: str = DbField(min_length=1, db_index=True, description="Стабильный id (slug)")
    name: str = DbField(min_length=1, max_length=64, description="agentskills name")
    description: str = DbField(
        min_length=1,
        max_length=1024,
        description="Tier-1: what the skill does and when to use it",
    )
    body_markdown: str = DbField(min_length=1, db_type="TEXT", description="Tier-2 procedure markdown")
    company_id: str = DbField(default="", db_index=True)
    agent_skill_row_id: str = DbField(default="", db_pk=True, db_type="TEXT")
    tool_refs: list[ToolReference] = DbField(
        default_factory=list,
        db_type="JSONB",
        description="Tools materialized into llm_node on load_agent_skill",
    )
    depends_on: list[str] = DbField(
        default_factory=list,
        description=(
            "agent_skill_id children loadable after this skill; "
            "arbitrary depth; cycles allowed; reload idempotent"
        ),
    )
    references: list[FileRef] = DbField(
        default_factory=list,
        db_type="JSONB",
        description="Tier-3 reference docs",
    )
    assets: list[FileRef] = DbField(
        default_factory=list,
        db_type="JSONB",
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

    @classmethod
    def skill_row_id_for_active_company(cls, agent_skill_id: str) -> str:
        """Ключ company_id:agent_skill_id из активной компании. Пустой agent_skill_id или компания — ValueError. Двоеточие — ValueError."""
        company_id = require_active_company().company_id
        if agent_skill_id == "" or company_id == "":
            raise ValueError("agent_skill_id is required")
        if ":" in agent_skill_id or ":" in company_id:
            raise ValueError("agent_skill_id and company_id must not contain ':'")
        return f"{company_id}:{agent_skill_id}"

    @model_validator(mode="after")
    def bind_company(self) -> AgentSkill:
        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("company_id is required")
        if self.company_id == "":
            self.company_id = company_id
        elif self.company_id != company_id:
            raise ValueError("company_id does not match the active company")
        expected = type(self).skill_row_id_for_active_company(self.agent_skill_id)
        if self.agent_skill_row_id == "":
            self.agent_skill_row_id = expected
        elif self.agent_skill_row_id != expected:
            raise ValueError("agent_skill_row_id does not match company_id and agent_skill_id")
        return self

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        expected = type(self).skill_row_id_for_active_company(self.agent_skill_id)
        if self.company_id == "" or self.agent_skill_row_id != expected:
            raise ValueError("agent_skill_row_id does not match the active company")

    def to_index_entry(self) -> AgentSkillIndexEntry:
        return AgentSkillIndexEntry(
            agent_skill_id=self.agent_skill_id,
            name=self.name,
            description=self.description,
        )

    @classmethod
    async def list_skills(cls, *, limit: int, offset: int) -> list[Self]:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        if offset < 0:
            raise ValueError("offset must be >= 0")
        return await cls.objects.order_by("agent_skill_id").limit(limit).offset(offset).all()

    @classmethod
    async def count_skills(cls) -> int:
        return await cls.objects.count()

    @classmethod
    async def require_by_agent_skill_id(cls, agent_skill_id: str) -> Self:
        skill = await cls.get(cls.skill_row_id_for_active_company(agent_skill_id))
        if skill is None:
            raise LookupError(f"AgentSkill not found: {agent_skill_id}")
        return skill

    @classmethod
    async def _persist(cls, skill: Self) -> bool:
        agent_skill_row_id = skill.agent_skill_row_id
        if agent_skill_row_id == "":
            raise ValueError("AgentSkill agent_skill_row_id is required")
        existing = await cls.objects.filter(agent_skill_row_id=agent_skill_row_id).get_or_none()
        if existing is None:
            _ = await cls.objects.create(instance=skill)
            return True
        _ = await skill.save()
        return True

    @classmethod
    async def _validate_depends_on_exist(cls, depends_on: list[str]) -> None:
        for dep_id in depends_on:
            dep = await cls.get(cls.skill_row_id_for_active_company(dep_id))
            if dep is None:
                raise ValueError(f"depends_on AgentSkill not found: {dep_id}")

    @classmethod
    async def _validate_tool_refs(cls, tool_refs: list[ToolReference]) -> None:
        builtins = builtin_tool_ids()
        for tool_ref in tool_refs:
            if tool_ref.code is not None and tool_ref.code.strip():
                continue
            if tool_ref.code_mode == CodeMode.MCP_TOOL:
                continue
            if tool_ref.tool_id in builtins:
                continue
            catalog_tool = await ToolReference.objects.filter(
                tool_row_id=ToolReference.row_id_for_active_company(tool_ref.tool_id)
            ).get_or_none()
            if catalog_tool is None:
                raise ValueError(
                    f"tool_refs tool_id not found in catalog or builtins: {tool_ref.tool_id}"
                )

    @classmethod
    async def create(cls, payload: Self) -> Self:
        existing = await cls.get(cls.skill_row_id_for_active_company(payload.agent_skill_id))
        if existing is not None:
            raise ValueError(f"AgentSkill already exists: {payload.agent_skill_id}")
        await cls._validate_tool_refs(payload.tool_refs)
        await cls._validate_depends_on_exist(payload.depends_on)
        saved_ok = await cls._persist(payload)
        if not saved_ok:
            raise RuntimeError(f"Failed to persist AgentSkill: {payload.agent_skill_id}")
        logger.info("flows.agent_skill", agent_skill_id=payload.agent_skill_id)
        return payload

    @classmethod
    async def update(cls, payload: AgentSkillUpdatePayload) -> Self:
        existing = await cls.require_by_agent_skill_id(payload.agent_skill_id)
        await cls._validate_tool_refs(payload.tool_refs)
        await cls._validate_depends_on_exist(payload.depends_on)
        skill = existing.model_copy(
            update={
                "name": payload.name,
                "description": payload.description,
                "body_markdown": payload.body_markdown,
                "tool_refs": payload.tool_refs,
                "depends_on": payload.depends_on,
                "references": payload.references,
                "assets": payload.assets,
            }
        )
        skill = cls.model_validate(skill.model_dump(mode="python"))
        saved_ok = await cls._persist(skill)
        if not saved_ok:
            raise RuntimeError(f"Failed to persist AgentSkill: {skill.agent_skill_id}")
        logger.info("flows.agent_skill", agent_skill_id=skill.agent_skill_id)
        return skill

    @classmethod
    async def delete_by_agent_skill_id(cls, agent_skill_id: str) -> None:
        row_id = cls.skill_row_id_for_active_company(agent_skill_id)
        if row_id == "":
            raise ValueError("AgentSkill agent_skill_row_id is required")
        deleted = await cls.objects.filter(agent_skill_row_id=row_id).delete()
        if not deleted:
            raise LookupError(f"AgentSkill not found: {agent_skill_id}")
        logger.info("flows.agent_skill", agent_skill_id=agent_skill_id)

    @classmethod
    async def resolve_index(cls, agent_skill_ids: list[str]) -> list[AgentSkillIndexEntry]:
        entries: list[AgentSkillIndexEntry] = []
        seen: set[str] = set()
        for agent_skill_id in agent_skill_ids:
            normalized = agent_skill_id.strip()
            if not normalized:
                raise ValueError("agent_skill_ids must not contain empty values")
            if normalized in seen:
                raise ValueError(f"duplicate agent_skill_id in attach list: {normalized}")
            seen.add(normalized)
            skill = await cls.require_by_agent_skill_id(normalized)
            entries.append(skill.to_index_entry())
        return entries

    @classmethod
    async def import_skill_md(
        cls,
        markdown: str,
        *,
        agent_skill_id: str | None = None,
        persist: bool = True,
    ) -> AgentSkill:
        parsed = parse_skill_md(markdown, agent_skill_id=agent_skill_id)
        await cls._validate_tool_refs(parsed.tool_refs)
        await cls._validate_depends_on_exist(parsed.depends_on)
        if not persist:
            return parsed
        existing = await cls.get(cls.skill_row_id_for_active_company(parsed.agent_skill_id))
        if existing is not None:
            raise ValueError(f"AgentSkill already exists: {parsed.agent_skill_id}")
        stored = cls.model_validate(parsed.model_dump(mode="python"))
        saved_ok = await cls._persist(stored)
        if not saved_ok:
            raise RuntimeError(f"Failed to persist AgentSkill: {stored.agent_skill_id}")
        logger.info("flows.agent_skill", agent_skill_id=stored.agent_skill_id)
        return stored


def parse_skill_md(markdown: str, *, agent_skill_id: str | None = None) -> AgentSkill:
    """Parse agentskills.io SKILL.md into AgentSkill (no persistence)."""
    text = markdown.strip()
    if not text:
        raise ValueError("SKILL.md content is empty")
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        raise ValueError("SKILL.md must start with YAML frontmatter delimited by ---")
    frontmatter_raw = match.group("frontmatter")
    body = match.group("body").strip()
    if not body:
        raise ValueError("SKILL.md body is empty")
    loaded_raw = parse_yaml_value(frontmatter_raw, "SKILL.md frontmatter")
    if not isinstance(loaded_raw, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    frontmatter = require_json_object(loaded_raw, "skill_md.frontmatter")

    name = _require_frontmatter_str(frontmatter, "name")
    description = _require_frontmatter_str(frontmatter, "description")
    resolved_id = (agent_skill_id or name).strip()
    # Obsolete frontmatter key `activation` is ignored (load is always via load_agent_skill).
    _ = frontmatter.pop("activation", None)
    depends_on = _parse_string_list(frontmatter.get("depends_on"), field_name="depends_on")
    tool_refs = _parse_allowed_tools(frontmatter.get("allowed-tools"))

    try:
        return AgentSkill(
            agent_skill_id=resolved_id,
            name=name,
            description=description,
            body_markdown=body,
            tool_refs=tool_refs,
            depends_on=depends_on,
            references=[],
            assets=[],
        )
    except ValidationError as exc:
        raise ValueError(f"Invalid AgentSkill from SKILL.md: {exc}") from exc


def _require_frontmatter_str(frontmatter: JsonObject, key: str) -> str:
    raw = frontmatter.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"SKILL.md frontmatter.{key} is required non-empty string")
    return raw.strip()


def _parse_string_list(raw: JsonValue | None, *, field_name: str) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.replace(",", " ").split()]
        return [part for part in parts if part]
    if isinstance(raw, list):
        result: list[str] = []
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"SKILL.md frontmatter.{field_name} entries must be strings")
            result.append(item.strip())
        return result
    raise ValueError(f"SKILL.md frontmatter.{field_name} must be string or list of strings")


def _parse_allowed_tools(raw: JsonValue | None) -> list[ToolReference]:
    if raw is None:
        return []
    tool_ids = _parse_string_list(raw, field_name="allowed-tools")
    refs: list[ToolReference] = []
    for tool_id in tool_ids:
        refs.append(
            ToolReference(
                tool_id=tool_id,
                description=f"Skill-bound tool {tool_id}",
                parameters_schema=dict(_EMPTY_OBJECT_SCHEMA),
            )
        )
    return refs


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
]
