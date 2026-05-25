"""Write closed conversation windows into LLM context memory."""

from __future__ import annotations

import hashlib
import json

from core.llm_context.memory import LLMContextMemoryEpisode, LLMContextMemoryStore
from core.llm_context.models import LLMContextMemoryScope, LLMContextProfile
from core.llm_context.token_counter import TiktokenTokenCounter, TokenCounter
from core.types import JsonObject, JsonValue

_SOURCE = "llm_context_compaction"
LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY = "llm_context_recall_content"
LLM_CONTEXT_MEMORY_SUMMARY_INSTRUCTION = (
    "Compress this closed conversation segment into durable episodic memory for future LLM context. "
    "Preserve the original language. Keep user preferences, decisions, constraints, open tasks, "
    "important entities, identifiers, and tool results. Remove filler and obsolete wording. "
    "Output only the compact memory, no preamble."
)


async def close_llm_context_memory_window(
    store: LLMContextMemoryStore,
    *,
    messages: list[JsonObject],
    policy: LLMContextProfile,
    cursor: int,
    session_id: str | None = None,
    flow_id: str | None = None,
    branch_id: str | None = None,
    node_id: str | None = None,
    user_id: str | None = None,
    token_counter: TokenCounter | None = None,
) -> int:
    """Persist the message prefix that no longer belongs to the active window."""
    episode, next_cursor = build_llm_context_memory_episode(
        messages=messages,
        policy=policy,
        cursor=cursor,
        session_id=session_id,
        flow_id=flow_id,
        branch_id=branch_id,
        node_id=node_id,
        user_id=user_id,
        token_counter=token_counter,
    )
    if episode is None:
        return next_cursor
    _ = await store.write_episode(episode)
    return next_cursor


def build_llm_context_memory_episode(
    *,
    messages: list[JsonObject],
    policy: LLMContextProfile,
    cursor: int,
    session_id: str | None = None,
    flow_id: str | None = None,
    branch_id: str | None = None,
    node_id: str | None = None,
    user_id: str | None = None,
    token_counter: TokenCounter | None = None,
) -> tuple[LLMContextMemoryEpisode | None, int]:
    """Build one closed memory episode without performing I/O."""
    if not _compaction_enabled(policy):
        return None, cursor

    safe_cursor = max(0, min(cursor, len(messages)))
    closed_end = _closed_prefix_end(
        messages,
        policy=policy,
        token_counter=token_counter or TiktokenTokenCounter(),
    )
    if closed_end <= safe_cursor:
        return None, safe_cursor

    closed_messages = messages[safe_cursor:closed_end]
    content = _render_episode_content(closed_messages)
    if not content:
        return None, closed_end

    scope = policy.memory
    metadata: JsonObject = {
        "cursor_start": safe_cursor,
        "cursor_end": closed_end,
        "message_count": len(closed_messages),
        "start_role": str(closed_messages[0].get("role", "")),
        "end_role": str(closed_messages[-1].get("role", "")),
        "content_hash": _content_hash(content),
    }
    memory_id = _memory_id(
        scope=scope,
        session_id=session_id,
        flow_id=flow_id,
        node_id=node_id,
        cursor=safe_cursor,
        closed_end=closed_end,
        content=content,
    )
    return (
        LLMContextMemoryEpisode(
            memory_id=memory_id,
            content=content,
            scope=scope,
            session_id=session_id,
            flow_id=flow_id,
            branch_id=branch_id,
            node_id=node_id,
            user_id=user_id,
            title=f"LLM context memory {safe_cursor}:{closed_end}",
            source=_SOURCE,
            metadata=metadata,
        ),
        closed_end,
    )


def compact_llm_context_memory_episode(
    episode: LLMContextMemoryEpisode,
    *,
    summary: str,
    token_counter: TokenCounter | None = None,
) -> LLMContextMemoryEpisode:
    """Replace a raw closed window with a compact summary before persistence."""
    compact_summary = summary.strip()
    if not compact_summary:
        raise ValueError("LLM context memory summary is empty")

    counter = token_counter or TiktokenTokenCounter()
    raw_content = episode.content.strip()
    content = _render_compacted_episode_content(compact_summary, raw_content)
    recall_content = _render_memory_recall_content(compact_summary)
    metadata = {
        **episode.metadata,
        "compaction": "llm_summary",
        LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY: recall_content,
        "raw_content_hash": _content_hash(raw_content),
        "raw_token_count": counter.count_text(raw_content),
        "summary_token_count": counter.count_text(compact_summary),
        "content_hash": _content_hash(content),
    }
    return episode.model_copy(update={"content": content, "metadata": metadata})


def llm_context_memory_cursor_key(
    *,
    scope: LLMContextMemoryScope,
    session_id: str | None = None,
    flow_id: str | None = None,
    node_id: str | None = None,
) -> str:
    """Cursor key for a runtime state that writes memory for one resolved scope."""
    if scope == "session":
        return f"session:{session_id or ''}"
    if scope == "node":
        return f"node:{flow_id or ''}:{node_id or ''}"
    if scope == "flow":
        return f"flow:{flow_id or ''}"
    if scope == "off":
        return "off"
    return f"company:{flow_id or ''}:{node_id or ''}"


def _compaction_enabled(policy: LLMContextProfile) -> bool:
    return (
        policy.mode != "off"
        and policy.memory != "off"
        and policy.compaction != "off"
    )


def _closed_prefix_end(
    messages: list[JsonObject],
    *,
    policy: LLMContextProfile,
    token_counter: TokenCounter,
) -> int:
    if len(messages) <= 1:
        return 0
    if policy.compaction == "force":
        return len(messages) - 1

    selected_tokens = token_counter.count_message(messages[-1])
    selected_start = len(messages) - 1
    for index in range(len(messages) - 2, -1, -1):
        token_count = token_counter.count_message(messages[index])
        if selected_tokens + token_count > policy.budget.active_window_tokens:
            break
        selected_tokens += token_count
        selected_start = index
    return selected_start


def _render_episode_content(messages: list[JsonObject]) -> str:
    rendered = "\n\n".join(
        part for part in (_render_message(message) for message in messages) if part
    )
    return rendered.strip()


def _render_compacted_episode_content(summary: str, raw_content: str) -> str:
    return (
        _render_memory_recall_content(summary)
        + "\n\n[Original closed conversation segment]\n"
        + raw_content.strip()
    )


def _render_memory_recall_content(summary: str) -> str:
    return "[Compacted conversation memory]\n" + summary.strip()


def _render_message(message: JsonObject) -> str:
    role = str(message.get("role") or "user")
    content = _content_to_text(message.get("content")).strip()
    tool_calls = message.get("tool_calls")
    tool_call_id = message.get("tool_call_id")

    parts = [f"[{role}]"]
    if content:
        parts.append(content)
    if tool_calls:
        parts.append("tool_calls=" + _stable_json(tool_calls))
    if tool_call_id:
        parts.append(f"tool_call_id={tool_call_id}")
    if len(parts) == 1:
        return ""
    return "\n".join(parts)


def _content_to_text(content: JsonValue) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "\n".join(text_parts)
    return _stable_json(content)


def _memory_id(
    *,
    scope: str,
    session_id: str | None,
    flow_id: str | None,
    node_id: str | None,
    cursor: int,
    closed_end: int,
    content: str,
) -> str:
    payload = {
        "scope": scope,
        "session_id": session_id,
        "flow_id": flow_id,
        "node_id": node_id,
        "cursor": cursor,
        "closed_end": closed_end,
        "content_hash": _content_hash(content),
    }
    return "ctxmem-" + hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()[:32]


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _stable_json(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


__all__ = [
    "build_llm_context_memory_episode",
    "close_llm_context_memory_window",
    "compact_llm_context_memory_episode",
    "LLM_CONTEXT_MEMORY_RECALL_CONTENT_METADATA_KEY",
    "LLM_CONTEXT_MEMORY_SUMMARY_INSTRUCTION",
    "llm_context_memory_cursor_key",
]
