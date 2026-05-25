"""Runtime memory source wiring for the generic LLM context layer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import Literal

from a2a.types import Message
from pydantic import Field

from core.clients.llm.messages import messages_to_openai
from core.llm_context import (
    LLMContextMemoryEpisode,
    LLMContextMemorySource,
    LLMContextMemoryStore,
    LLMContextProfile,
    build_llm_context_memory_episode,
    compact_llm_context_memory_episode,
    llm_context_memory_cursor_key,
)
from core.llm_context.models import LLMContextMemoryScope
from core.models import StrictBaseModel
from core.state import ExecutionState
from core.types import JsonObject

RuntimeMemoryCompaction = Literal["raw", "llm_summary"]


class RuntimeMemoryEpisodePayload(StrictBaseModel):
    """Deterministic memory episode payload stored in durable activity input."""

    memory_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    scope: LLMContextMemoryScope
    session_id: str | None = None
    flow_id: str | None = None
    branch_id: str | None = None
    node_id: str | None = None
    user_id: str | None = None
    title: str | None = None
    source: str = Field(..., min_length=1)
    metadata: JsonObject = Field(default_factory=dict)

    @classmethod
    def from_episode(cls, episode: LLMContextMemoryEpisode) -> "RuntimeMemoryEpisodePayload":
        return cls.model_validate(episode.model_dump(mode="python", exclude={"created_at"}))

    def to_episode(self) -> LLMContextMemoryEpisode:
        return LLMContextMemoryEpisode(
            memory_id=self.memory_id,
            content=self.content,
            scope=self.scope,
            session_id=self.session_id,
            flow_id=self.flow_id,
            branch_id=self.branch_id,
            node_id=self.node_id,
            user_id=self.user_id,
            title=self.title,
            source=self.source,
            metadata=self.metadata,
            created_at=datetime.now(timezone.utc),
        )


class RuntimeMemoryCloseDecision(StrictBaseModel):
    """Pure decision for closing the current LLM context memory window."""

    cursor_key: str = Field(..., min_length=1)
    cursor: int = Field(..., ge=0)
    next_cursor: int = Field(..., ge=0)
    episode: RuntimeMemoryEpisodePayload | None
    compaction: RuntimeMemoryCompaction


class RuntimeMemoryWriteCommand(StrictBaseModel):
    """Durable command executed as exactly-once memory activity."""

    session_id: str = Field(..., min_length=1)
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=0)
    node_id: str = Field(..., min_length=1)
    cursor_key: str = Field(..., min_length=1)
    cursor: int = Field(..., ge=0)
    next_cursor: int = Field(..., ge=0)
    episode: RuntimeMemoryEpisodePayload
    compaction: RuntimeMemoryCompaction


class RuntimeMemoryWriteResult(StrictBaseModel):
    """Typed memory activity result applied to runtime state projection."""

    memory_id: str = Field(..., min_length=1)
    cursor_key: str = Field(..., min_length=1)
    next_cursor: int = Field(..., ge=0)
    scope: LLMContextMemoryScope
    compaction: RuntimeMemoryCompaction
    written: Literal[True] = True


def resolve_memory_context_source_for_runtime(
    *,
    store: LLMContextMemoryStore,
    state: ExecutionState | None,
    node_id: str,
) -> LLMContextMemorySource | None:
    """Create a memory source scoped to the current flow execution state."""
    if state is None:
        return None
    return LLMContextMemorySource(
        store=store,
        session_id=state.session_id,
        flow_id=state.session_flow_id,
        branch_id=state.branch_id,
        node_id=node_id,
        user_id=state.user_id,
    )


def build_state_messages_memory_close_decision(
    *,
    state: ExecutionState,
    node_id: str,
    policy: LLMContextProfile | None,
    messages: Sequence[Message | JsonObject | str],
    compaction: RuntimeMemoryCompaction = "llm_summary",
) -> RuntimeMemoryCloseDecision | None:
    """Build a deterministic memory close decision without performing I/O."""
    if policy is None:
        return None
    if policy.mode == "off" or policy.memory == "off" or policy.compaction == "off":
        return None

    session_id = state.session_id
    flow_id = state.session_flow_id
    branch_id = state.branch_id
    user_id = state.user_id
    key = llm_context_memory_cursor_key(
        scope=policy.memory,
        session_id=session_id,
        flow_id=flow_id,
        node_id=node_id,
    )
    cursor_map = dict(state.llm_context_memory_cursor)
    cursor = cursor_map.get(key, 0)
    episode, next_cursor = build_llm_context_memory_episode(
        messages=messages_to_openai(messages),
        policy=policy,
        cursor=cursor,
        session_id=session_id,
        flow_id=flow_id,
        branch_id=branch_id,
        node_id=node_id,
        user_id=user_id,
    )
    if next_cursor == cursor:
        return None
    return RuntimeMemoryCloseDecision(
        cursor_key=key,
        cursor=cursor,
        next_cursor=next_cursor,
        episode=RuntimeMemoryEpisodePayload.from_episode(episode) if episode is not None else None,
        compaction=compaction,
    )


async def write_runtime_memory_episode(
    *,
    store: LLMContextMemoryStore,
    command: RuntimeMemoryWriteCommand,
    summarize_episode: Callable[[str], Awaitable[str]] | None,
) -> RuntimeMemoryWriteResult:
    """Execute one typed memory write command. Caller owns durable activity journaling."""
    episode = command.episode.to_episode()
    if command.compaction == "llm_summary":
        if summarize_episode is None:
            raise RuntimeError("llm_summary memory command requires summarize_episode")
        summary = await summarize_episode(episode.content)
        episode = compact_llm_context_memory_episode(episode, summary=summary)

    written_memory_id = await store.write_episode(episode)
    if written_memory_id != episode.memory_id:
        raise RuntimeError(
            "Memory store returned unexpected memory_id: "
            + f"expected={episode.memory_id!r}, actual={written_memory_id!r}"
        )
    return RuntimeMemoryWriteResult(
        memory_id=episode.memory_id,
        cursor_key=command.cursor_key,
        next_cursor=command.next_cursor,
        scope=episode.scope,
        compaction=command.compaction,
        written=True,
    )


def apply_runtime_memory_cursor_advance(
    state: ExecutionState,
    decision: RuntimeMemoryCloseDecision,
) -> None:
    """Apply a pure cursor-only close decision to state projection."""
    cursor_map = dict(state.llm_context_memory_cursor)
    cursor_map[decision.cursor_key] = max(
        cursor_map.get(decision.cursor_key, 0),
        decision.next_cursor,
    )
    state.llm_context_memory_cursor = cursor_map


def apply_runtime_memory_write_result(
    state: ExecutionState,
    result: RuntimeMemoryWriteResult,
) -> None:
    """Apply completed memory write result to state projection."""
    cursor_map = dict(state.llm_context_memory_cursor)
    cursor_map[result.cursor_key] = max(
        cursor_map.get(result.cursor_key, 0),
        result.next_cursor,
    )
    state.llm_context_memory_cursor = cursor_map


def prune_state_messages_to_memory_cursor_for_runtime(state: ExecutionState) -> int:
    """
    Physically drop the message prefix already closed by every memory cursor.

    Cursor values are indexes into ``state.messages``. After pruning the shared prefix, all
    cursors are rebased to the shorter runtime projection.
    """
    messages = list(state.messages)
    if len(messages) <= 1:
        return 0
    cursor_map = dict(state.llm_context_memory_cursor)
    if not cursor_map:
        return 0

    prune_count = min(cursor_map.values(), default=0)
    prune_count = min(prune_count, len(messages) - 1)
    if prune_count <= 0:
        return 0

    state.messages = messages[prune_count:]
    state.llm_context_memory_cursor = {
        key: max(0, value - prune_count)
        for key, value in cursor_map.items()
    }
    return prune_count


__all__ = [
    "RuntimeMemoryCloseDecision",
    "RuntimeMemoryEpisodePayload",
    "RuntimeMemoryWriteCommand",
    "RuntimeMemoryWriteResult",
    "apply_runtime_memory_cursor_advance",
    "apply_runtime_memory_write_result",
    "build_state_messages_memory_close_decision",
    "prune_state_messages_to_memory_cursor_for_runtime",
    "resolve_memory_context_source_for_runtime",
    "write_runtime_memory_episode",
]
