"""Runtime host for progressive Agent Skill load inside LlmNodeRunner."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from apps.flows.src.models.agent_skill import AgentSkill, AgentSkillIndexEntry
from apps.flows.src.models.tool_reference import ToolReference
from apps.flows.src.tools.base import BaseTool
from core.llm_context.models import LLMContextBlock


@dataclass
class AgentSkillRuntimeHost:
    """Mutable session state for skills attached to one llm_node run."""

    attached_ids: frozenset[str]
    index_entries: tuple[AgentSkillIndexEntry, ...]
    loaded_depths: dict[str, int] = field(default_factory=dict)
    context_blocks: list[LLMContextBlock] = field(default_factory=list)
    pending_tool_refs: list[ToolReference] = field(default_factory=list)
    loaded_skills: dict[str, AgentSkill] = field(default_factory=dict)

    def ensure_index_block(self) -> None:
        if any(block.stable_key == "agent_skills.index" for block in self.context_blocks):
            return
        if not self.index_entries:
            return
        lines = [
            "Available Agent Skills (call load_agent_skill to activate full instructions):",
        ]
        for entry in self.index_entries:
            lines.append(
                f"- {entry.agent_skill_id} ({entry.name}): {entry.description}"
            )
        self.context_blocks.append(
            LLMContextBlock(
                kind="skill",
                budget_scope="skill",
                role="system",
                content="\n".join(lines),
                stable_key="agent_skills.index",
                priority=40,
                required=True,
                provenance={"source": "agent_skills", "tier": "index"},
            )
        )


_AGENT_SKILL_RUNTIME_HOST: ContextVar[AgentSkillRuntimeHost | None] = ContextVar(
    "flows_agent_skill_runtime_host",
    default=None,
)


def get_agent_skill_runtime_host() -> AgentSkillRuntimeHost | None:
    return _AGENT_SKILL_RUNTIME_HOST.get()


def require_agent_skill_runtime_host() -> AgentSkillRuntimeHost:
    host = _AGENT_SKILL_RUNTIME_HOST.get()
    if host is None:
        raise RuntimeError("AgentSkillRuntimeHost is not active for this tool call")
    return host


@contextmanager
def agent_skill_runtime_host_scope(
    host: AgentSkillRuntimeHost,
) -> Generator[AgentSkillRuntimeHost, None, None]:
    token = _AGENT_SKILL_RUNTIME_HOST.set(host)
    try:
        yield host
    finally:
        _AGENT_SKILL_RUNTIME_HOST.reset(token)


def merge_tools_by_name(existing: list[BaseTool], new_tools: list[BaseTool]) -> list[BaseTool]:
    """Append tools whose names are not already present."""
    known = {tool.name for tool in existing}
    merged = list(existing)
    for tool in new_tools:
        if tool.name in known:
            continue
        known.add(tool.name)
        merged.append(tool)
    return merged


__all__ = [
    "AgentSkillRuntimeHost",
    "agent_skill_runtime_host_scope",
    "get_agent_skill_runtime_host",
    "merge_tools_by_name",
    "require_agent_skill_runtime_host",
]
