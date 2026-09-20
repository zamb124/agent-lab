"""Сервис catalog Agent Skills: CRUD, index, SKILL.md import."""

from __future__ import annotations

import re
from typing import cast

import yaml
from pydantic import ValidationError

from apps.flows.src.db.agent_skill_repository import AgentSkillRepository
from apps.flows.src.db.tool_repository import ToolRepository
from apps.flows.src.models.agent_skill import (
    AgentSkill,
    AgentSkillIndexEntry,
    AgentSkillUpdatePayload,
)
from apps.flows.src.models.enums import CodeMode
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.tools.builtin_specs import builtin_tool_ids
from core.logging import get_logger
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<frontmatter>.*?)\n---\s*\n(?P<body>.*)\Z",
    re.DOTALL,
)

_EMPTY_OBJECT_SCHEMA: JsonObject = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


class AgentSkillService:
    """Business logic for AgentSkill catalog."""

    def __init__(
        self,
        repository: AgentSkillRepository,
        tool_repository: ToolRepository,
    ) -> None:
        self._repository: AgentSkillRepository = repository
        self._tool_repository: ToolRepository = tool_repository

    async def list_skills(self, *, limit: int, offset: int) -> list[AgentSkill]:
        return await self._repository.list(limit=limit, offset=offset)

    async def count_skills(self) -> int:
        return await self._repository.count_all()

    async def get(self, agent_skill_id: str) -> AgentSkill:
        skill = await self._repository.get(agent_skill_id)
        if skill is None:
            raise LookupError(f"AgentSkill not found: {agent_skill_id}")
        return skill

    async def create(self, payload: AgentSkill) -> AgentSkill:
        existing = await self._repository.get(payload.agent_skill_id)
        if existing is not None:
            raise ValueError(f"AgentSkill already exists: {payload.agent_skill_id}")
        await self._validate_tool_refs(payload.tool_refs)
        await self._validate_depends_on_exist(payload.depends_on)
        saved_ok = await self._repository.set(payload)
        if not saved_ok:
            raise RuntimeError(f"Failed to persist AgentSkill: {payload.agent_skill_id}")
        logger.info("agent_skill.created agent_skill_id=%s", payload.agent_skill_id)
        return payload

    async def update(self, payload: AgentSkillUpdatePayload) -> AgentSkill:
        existing = await self.get(payload.agent_skill_id)
        await self._validate_tool_refs(payload.tool_refs)
        await self._validate_depends_on_exist(payload.depends_on)
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
        skill = AgentSkill.model_validate(skill.model_dump(mode="python"))
        saved_ok = await self._repository.set(skill)
        if not saved_ok:
            raise RuntimeError(f"Failed to persist AgentSkill: {skill.agent_skill_id}")
        logger.info("agent_skill.updated agent_skill_id=%s", skill.agent_skill_id)
        return skill

    async def delete(self, agent_skill_id: str) -> None:
        deleted = await self._repository.delete(agent_skill_id)
        if not deleted:
            raise LookupError(f"AgentSkill not found: {agent_skill_id}")
        logger.info("agent_skill.deleted agent_skill_id=%s", agent_skill_id)

    async def resolve_index(self, agent_skill_ids: list[str]) -> list[AgentSkillIndexEntry]:
        entries: list[AgentSkillIndexEntry] = []
        seen: set[str] = set()
        for agent_skill_id in agent_skill_ids:
            normalized = agent_skill_id.strip()
            if not normalized:
                raise ValueError("agent_skill_ids must not contain empty values")
            if normalized in seen:
                raise ValueError(f"duplicate agent_skill_id in attach list: {normalized}")
            seen.add(normalized)
            skill = await self.get(normalized)
            entries.append(skill.to_index_entry())
        return entries

    async def import_skill_md(
        self,
        markdown: str,
        *,
        agent_skill_id: str | None = None,
        persist: bool = True,
    ) -> AgentSkill:
        parsed = parse_skill_md(markdown, agent_skill_id=agent_skill_id)
        await self._validate_tool_refs(parsed.tool_refs)
        await self._validate_depends_on_exist(parsed.depends_on)
        if not persist:
            return parsed
        existing = await self._repository.get(parsed.agent_skill_id)
        if existing is not None:
            raise ValueError(f"AgentSkill already exists: {parsed.agent_skill_id}")
        saved_ok = await self._repository.set(parsed)
        if not saved_ok:
            raise RuntimeError(f"Failed to persist AgentSkill: {parsed.agent_skill_id}")
        logger.info("agent_skill.imported agent_skill_id=%s", parsed.agent_skill_id)
        return parsed

    async def _validate_depends_on_exist(self, depends_on: list[str]) -> None:
        for dep_id in depends_on:
            dep = await self._repository.get(dep_id)
            if dep is None:
                raise ValueError(f"depends_on AgentSkill not found: {dep_id}")

    async def _validate_tool_refs(self, tool_refs: list[ToolReference]) -> None:
        builtins = builtin_tool_ids()
        for tool_ref in tool_refs:
            if tool_ref.code is not None and tool_ref.code.strip():
                continue
            if tool_ref.code_mode == CodeMode.MCP_TOOL:
                continue
            if tool_ref.tool_id in builtins:
                continue
            catalog_tool = await self._tool_repository.get(tool_ref.tool_id)
            if catalog_tool is None:
                raise ValueError(
                    f"tool_refs tool_id not found in catalog or builtins: {tool_ref.tool_id}"
                )


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
    loaded_raw: object = cast(object, yaml.safe_load(frontmatter_raw))
    if not isinstance(loaded_raw, dict):
        raise ValueError("SKILL.md frontmatter must be a YAML mapping")
    frontmatter = require_json_object(cast(object, loaded_raw), "skill_md.frontmatter")

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


__all__ = [
    "AgentSkillService",
    "parse_skill_md",
]
