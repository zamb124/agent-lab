"""Builtin meta-tools for progressive Agent Skill loading."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.flows.src.models.agent_skill import AgentSkill
from apps.flows.src.runtime.agent_skill_runtime import (
    AgentSkillRuntimeHost,
    require_agent_skill_runtime_host,
)
from apps.flows.src.services.flow_ui_cards import show_skill_activity
from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.files_client import FilesClient
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
        description=(
            "file_id of a reference/asset FileRef from load_agent_skill for this skill; "
            "never a Documents library / SPA UI file_id"
        ),
    )
    original_name: str | None = Field(
        default=None,
        description=(
            "Prefer original_name from load_agent_skill references/assets "
            "(e.g. documents-employee-methodology.md)"
        ),
    )


@tool(
    name="load_agent_skill",
    description=(
        "Load full Agent Skill instructions into context and unlock that skill's tools. "
        "Use when the task matches a skill from the available skills index."
    ),
    tags=["flows"],
    parameters_model=LoadAgentSkillArgs,
    permission=list(STANDARD_USER_TOOL_GROUPS),
)
async def load_agent_skill(agent_skill_id: str, *, state: "ExecutionState") -> JsonObject:
    host = require_agent_skill_runtime_host()
    skill_id = agent_skill_id.strip()
    if not skill_id:
        raise ValueError("agent_skill_id is required")

    if skill_id in host.loaded_depths:
        payload: JsonObject = {
            "success": True,
            "agent_skill_id": skill_id,
            "already_loaded": True,
            "depth": host.loaded_depths[skill_id],
        }
        loaded = host.loaded_skills.get(skill_id)
        if loaded is not None:
            payload["name"] = loaded.name
        return payload

    depth = _resolve_load_depth(host, skill_id)
    skill = await AgentSkill.require_by_agent_skill_id(skill_id)
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
    result: JsonObject = {
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
    _ = show_skill_activity(state, agent_skill_id=skill_id, title=skill.name, status="loaded")
    return result


@tool(
    name="read_agent_skill_reference",
    description=(
        "Read a Tier-3 methodology/asset file listed in a loaded Agent Skill "
        "references/assets (from load_agent_skill). Prefer original_name. "
        "Not for Documents library or SPA UI file_id — use documents_read after "
        "loading documents-catalog."
    ),
    tags=["flows"],
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
    raw = await FilesClient().get_bytes(matched.file_id)
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


# Engineering safety stop for runaway nesting (not a product depth cap).
_AGENT_SKILL_LOAD_DEPTH_SAFETY_STOP = 64


def _resolve_load_depth(host: AgentSkillRuntimeHost, skill_id: str) -> int:
    """Resolve load depth: attached=0; child of any loaded parent = parent_depth+1.

    Cycles in depends_on are allowed: reload is idempotent at the call site.
    """
    if skill_id in host.attached_ids:
        return 0
    best_depth: int | None = None
    for loaded_id, loaded_depth in host.loaded_depths.items():
        loaded_skill = host.loaded_skills.get(loaded_id)
        if loaded_skill is None:
            continue
        if skill_id not in loaded_skill.depends_on:
            continue
        candidate = loaded_depth + 1
        if best_depth is None or candidate < best_depth:
            best_depth = candidate
    if best_depth is None:
        raise ValueError(
            f"AgentSkill {skill_id!r} is not attached to this llm_node "
            + "and is not a depends_on of a loaded skill"
        )
    if best_depth >= _AGENT_SKILL_LOAD_DEPTH_SAFETY_STOP:
        raise ValueError(
            f"AgentSkill {skill_id!r} load depth {best_depth} exceeds safety stop {_AGENT_SKILL_LOAD_DEPTH_SAFETY_STOP}"
        )
    return best_depth


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
