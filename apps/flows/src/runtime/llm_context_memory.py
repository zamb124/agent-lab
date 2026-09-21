"""Подключение memory source для общего LLM context layer в runtime."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

from a2a.types import Message
from pydantic import Field

from core.clients.llm.messages import messages_to_openai
from core.llm_context import LLMContextProfile
from core.llm_context.memory import (
    LLMContextMemoryEpisode,
    LLMContextMemorySource,
    LLMContextMemoryStore,
)
from core.llm_context.memory_compaction import (
    build_llm_context_memory_episode,
    compact_llm_context_memory_episode,
    llm_context_memory_cursor_key,
)
from core.llm_context.models import LLMContextMemoryScope
from core.models import StrictBaseModel
from core.state import ExecutionState
from core.types import JsonObject

RuntimeMemoryCompaction = Literal["raw", "llm_summary"]


class RuntimeMemoryCloseDecision(StrictBaseModel):
    """Чистое решение о закрытии текущего окна LLM context memory."""

    cursor_key: str = Field(..., min_length=1)
    cursor: int = Field(..., ge=0)
    next_cursor: int = Field(..., ge=0)
    episode: LLMContextMemoryEpisode | None
    compaction: RuntimeMemoryCompaction


class RuntimeMemoryWriteCommand(StrictBaseModel):
    """Durable-команда, исполняемая как exactly-once memory activity."""

    session_id: str = Field(..., min_length=1)
    execution_branch_id: str = Field(..., min_length=1)
    node_schedule_sequence: int = Field(..., ge=0)
    node_id: str = Field(..., min_length=1)
    cursor_key: str = Field(..., min_length=1)
    cursor: int = Field(..., ge=0)
    next_cursor: int = Field(..., ge=0)
    episode: LLMContextMemoryEpisode
    compaction: RuntimeMemoryCompaction


class RuntimeMemoryWriteResult(StrictBaseModel):
    """Типизированный результат memory activity для проекции runtime state."""

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
    """Создаёт memory source в области текущего flow execution state."""
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
    """Собирает детерминированное решение о закрытии памяти без I/O."""
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
        episode=episode,
        compaction=compaction,
    )


async def write_runtime_memory_episode(
    *,
    store: LLMContextMemoryStore,
    command: RuntimeMemoryWriteCommand,
    summarize_episode: Callable[[str], Awaitable[str]] | None,
) -> RuntimeMemoryWriteResult:
    """Выполняет одну типизированную memory write-команду. Журналирование activity — у вызывающего."""
    episode = command.episode
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
    """Применяет чистое решение о закрытии (только cursor) к проекции state."""
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
    """Применяет завершённый результат memory write к проекции state."""
    cursor_map = dict(state.llm_context_memory_cursor)
    cursor_map[result.cursor_key] = max(
        cursor_map.get(result.cursor_key, 0),
        result.next_cursor,
    )
    state.llm_context_memory_cursor = cursor_map


def prune_state_messages_to_memory_cursor_for_runtime(state: ExecutionState) -> int:
    """
    Физически отбрасывает префикс сообщений, уже закрытый всеми memory cursor.

    Значения cursor — индексы в ``state.messages``. После обрезки общего префикса все
    cursor пересчитываются относительно укороченной runtime-проекции.
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
    "RuntimeMemoryWriteCommand",
    "RuntimeMemoryWriteResult",
    "apply_runtime_memory_cursor_advance",
    "apply_runtime_memory_write_result",
    "build_state_messages_memory_close_decision",
    "prune_state_messages_to_memory_cursor_for_runtime",
    "resolve_memory_context_source_for_runtime",
    "write_runtime_memory_episode",
]
