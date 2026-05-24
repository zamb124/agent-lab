"""Runtime memory source wiring for the generic LLM context layer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from core.clients.llm.messages import messages_to_openai
from core.llm_context import (
    LLMContextMemorySource,
    LLMContextMemoryStore,
    LLMContextProfile,
    build_llm_context_memory_episode,
    compact_llm_context_memory_episode,
    llm_context_memory_cursor_key,
)
from core.logging import get_logger
from core.utils.background import run_with_log_context

logger = get_logger(__name__)


def resolve_memory_context_source_for_runtime(
    *,
    store: Any,
    state: Any,
    node_id: str,
) -> LLMContextMemorySource | None:
    """Create a memory source scoped to the current flow execution state."""
    if state is None:
        return None
    return LLMContextMemorySource(
        store=store,
        session_id=getattr(state, "session_id", None),
        flow_id=getattr(state, "session_flow_id", None),
        branch_id=getattr(state, "branch_id", None),
        node_id=node_id,
        user_id=getattr(state, "user_id", None),
    )


def schedule_state_messages_to_memory_for_runtime(
    *,
    store: LLMContextMemoryStore,
    state: Any,
    node_id: str,
    policy: LLMContextProfile | None,
    messages: list[Any],
    summarize_episode: Callable[[str], Awaitable[str]] | None = None,
    after_write: Callable[[], Awaitable[None]] | None = None,
) -> bool:
    """Schedule persistence of the closed runtime message window into generic memory."""
    if state is None or policy is None:
        return False
    if policy.mode == "off" or policy.memory == "off" or policy.compaction == "off":
        return False

    session_id = getattr(state, "session_id", None)
    flow_id = getattr(state, "session_flow_id", None)
    branch_id = getattr(state, "branch_id", None)
    user_id = getattr(state, "user_id", None)
    key = llm_context_memory_cursor_key(
        scope=policy.memory,
        session_id=session_id,
        flow_id=flow_id,
        node_id=node_id,
    )
    cursor_map = dict(getattr(state, "llm_context_memory_cursor", {}) or {})
    cursor = int(cursor_map.get(key, 0))
    try:
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
    except Exception as exc:
        logger.exception(
            "llm_context.memory_schedule_failed",
            flow_id=flow_id,
            node_id=node_id,
            session_id=session_id,
            **{"exception.type": type(exc).__name__},
        )
        return False
    if next_cursor == cursor:
        return False
    if episode is None:
        cursor_map[key] = next_cursor
        state.llm_context_memory_cursor = cursor_map
        return True

    async def write_episode() -> None:
        try:
            episode_to_write = episode
            if summarize_episode is not None:
                summary = await summarize_episode(episode.content)
                episode_to_write = compact_llm_context_memory_episode(
                    episode,
                    summary=summary,
                )
            await store.write_episode(episode_to_write)
            latest_cursor_map = dict(getattr(state, "llm_context_memory_cursor", {}) or {})
            latest_cursor_map[key] = max(int(latest_cursor_map.get(key, 0)), next_cursor)
            state.llm_context_memory_cursor = latest_cursor_map
            if after_write is not None:
                await after_write()
        except Exception as exc:
            logger.exception(
                "llm_context.memory_write_failed",
                memory_id=episode.memory_id,
                flow_id=episode.flow_id,
                node_id=episode.node_id,
                session_id=episode.session_id,
                **{"exception.type": type(exc).__name__},
            )

    run_with_log_context(
        write_episode(),
        name="llm_context_memory_write",
        background_kind="llm_context_memory",
        extra={
            "memory_id": episode.memory_id,
            "flow_id": episode.flow_id,
            "node_id": episode.node_id,
            "session_id": episode.session_id,
        },
    )
    return True


def prune_state_messages_to_memory_cursor_for_runtime(state: Any) -> int:
    """
    Physically drop the message prefix already closed by every memory cursor.

    Cursor values are indexes into ``state.messages``. After pruning the shared prefix, all
    cursors are rebased to the shorter hot state.
    """
    if state is None:
        return 0
    messages = list(getattr(state, "messages", None) or [])
    if len(messages) <= 1:
        return 0
    raw_cursor_map = getattr(state, "llm_context_memory_cursor", {}) or {}
    if not isinstance(raw_cursor_map, dict) or not raw_cursor_map:
        return 0

    cursor_map: dict[str, int] = {
        str(key): max(0, int(value))
        for key, value in raw_cursor_map.items()
    }
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
    "prune_state_messages_to_memory_cursor_for_runtime",
    "resolve_memory_context_source_for_runtime",
    "schedule_state_messages_to_memory_for_runtime",
]
