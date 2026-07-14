"""Builtin meta-tools for progressive Agent Skill loading."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    require_agent_skill_runtime_host,
)
from apps.flows.src.services.platform_facades import get_agent_skill_service, get_file_bytes
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.files.file_ref import FileRef
from core.llm_context.models import LLMContextBlock
from core.types import JsonObject

if TYPE_CHECKING:
    from core.state import ExecutionState


class LoadAgentSkillArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    agent_skill_id: str = Field(
        ...,
        min_length=1,
        description="Id of an Agent Skill attached to this llm_node (or depends_on of a loaded skill).",
    )


class ReadAgentSkillReferenceArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    agent_skill_id: str = Field(..., min_length=1, description="Loaded Agent Skill id")
    file_id: str | None = Field(
        default=None,
        description="file_id of a reference/asset FileRef on the skill",
    )
    original_name: str | None = Field(
        default=None,
        description="original_name of a reference/asset FileRef on the skill",
    )


@tool(
    name="load_agent_skill",
    description=(
        "Load full Agent Skill instructions into context and unlock that skill's tools. "
        "Use when the task matches a skill from the available skills index."
    ),
    tags=["agent_skills", "context"],
    parameters_model=LoadAgentSkillArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def load_agent_skill(agent_skill_id: str, *, state: "ExecutionState") -> JsonObject:
    _ = state
    host = require_agent_skill_runtime_host()
    skill_id = agent_skill_id.strip()
    if not skill_id:
        raise ValueError("agent_skill_id is required")

    if skill_id in host.loaded_depths:
        return {
            "success": True,
            "agent_skill_id": skill_id,
            "already_loaded": True,
            "depth": host.loaded_depths[skill_id],
        }

    depth = _resolve_load_depth(host, skill_id)
    skill = await get_agent_skill_service().get(skill_id)
    body_key = f"agent_skills.body.{skill_id}"
    if not any(block.stable_key == body_key for block in host.context_blocks):
        host.context_blocks.append(
            LLMContextBlock(
                kind="skill",
                budget_scope="skill",
                role="system",
                content=(
                    f"Agent Skill `{skill_id}` ({skill.name}) instructions:\n\n"
                    f"{skill.body_markdown}"
                ),
                stable_key=body_key,
                priority=45,
                required=False,
                provenance={
                    "source": "agent_skills",
                    "tier": "body",
                    "agent_skill_id": skill_id,
                },
            )
        )

    if skill.tool_refs:
        host.pending_tool_refs.extend(skill.tool_refs)

    host.loaded_depths[skill_id] = depth
    host.loaded_skills[skill_id] = skill
    return {
        "success": True,
        "agent_skill_id": skill_id,
        "name": skill.name,
        "already_loaded": False,
        "depth": depth,
        "tools_unlocked": [ref.tool_id for ref in skill.tool_refs],
        "depends_on": list(skill.depends_on),
        "references": [_file_ref_brief(ref) for ref in skill.references],
        "assets": [_file_ref_brief(ref) for ref in skill.assets],
    }


@tool(
    name="read_agent_skill_reference",
    description=(
        "Read a Tier-3 reference or asset file belonging to a loaded Agent Skill "
        "(by file_id or original_name)."
    ),
    tags=["agent_skills", "files"],
    parameters_model=ReadAgentSkillReferenceArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def read_agent_skill_reference(
    agent_skill_id: str,
    file_id: str | None = None,
    original_name: str | None = None,
    *,
    state: "ExecutionState",
) -> JsonObject:
    _ = state
    host = require_agent_skill_runtime_host()
    skill_id = agent_skill_id.strip()
    if skill_id not in host.loaded_skills:
        raise ValueError(f"AgentSkill is not loaded: {skill_id}")
    if (file_id is None or not file_id.strip()) and (
        original_name is None or not original_name.strip()
    ):
        raise ValueError("Provide file_id or original_name")

    skill = host.loaded_skills[skill_id]
    candidates = list(skill.references) + list(skill.assets)
    matched = _match_file_ref(
        candidates,
        file_id=file_id.strip() if file_id else None,
        original_name=original_name.strip() if original_name else None,
    )
    if matched.file_id is None or not matched.file_id.strip():
        raise ValueError(
            f"AgentSkill {skill_id} file {matched.original_name!r} has no file_id"
        )
    raw = await get_file_bytes(matched.file_id)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"AgentSkill reference {matched.original_name!r} is not UTF-8 text"
        ) from exc
    return {
        "success": True,
        "agent_skill_id": skill_id,
        "file_id": matched.file_id,
        "original_name": matched.original_name,
        "content_type": matched.content_type,
        "content": text,
    }


def _resolve_load_depth(host: AgentSkillRuntimeHost, skill_id: str) -> int:
    if skill_id in host.attached_ids:
        return 0
    for loaded_id, loaded_depth in host.loaded_depths.items():
        if loaded_depth != 0:
            continue
        loaded_skill = host.loaded_skills.get(loaded_id)
        if loaded_skill is None:
            continue
        if skill_id in loaded_skill.depends_on:
            return 1
    raise ValueError(
        f"AgentSkill {skill_id!r} is not attached to this llm_node "
        + "and is not a depends_on of a loaded depth-0 skill"
    )


def _match_file_ref(
    candidates: list[FileRef],
    *,
    file_id: str | None,
    original_name: str | None,
) -> FileRef:
    for ref in candidates:
        if file_id is not None and ref.file_id == file_id:
            return ref
        if original_name is not None and ref.original_name == original_name:
            return ref
    raise ValueError(
        f"No skill file matched file_id={file_id!r} original_name={original_name!r}"
    )


def _file_ref_brief(ref: FileRef) -> JsonObject:
    return {
        "file_id": ref.file_id,
        "original_name": ref.original_name,
        "content_type": ref.content_type,
        "file_size": ref.file_size,
    }


__all__ = [
    "LoadAgentSkillArgs",
    "ReadAgentSkillReferenceArgs",
    "load_agent_skill",
    "read_agent_skill_reference",
]
