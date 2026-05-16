"""Scheduling tool state identifiers."""

from __future__ import annotations


from core.state import ExecutionState


def extract_ids_from_state(state: ExecutionState) -> tuple[str, str, str]:
    """
    Извлекает flow_id, session_id, user_id из state.

    session_id обязателен и всегда в формате 'flow_id:context_id'.
    """
    session_id = state.session_id
    if not session_id:
        raise ValueError("session_id is required in state for scheduling tools")

    if ":" not in session_id:
        raise ValueError(
            f"session_id must be in format 'flow_id:context_id', got: '{session_id}'"
        )

    flow_id = session_id.split(":")[0]
    user_id = state.user_id or ""

    return flow_id, session_id, user_id


__all__ = ["extract_ids_from_state"]
