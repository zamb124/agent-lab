"""Tool authz gate bound from FlowContainer (breaks tools↔container import cycle)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

ToolAuthzGate = Callable[
    [Sequence[str] | None, str, str],
    Awaitable[str | None],
]

_gate: ToolAuthzGate | None = None


def bind_tool_authz_gate(gate: ToolAuthzGate) -> None:
    global _gate
    _gate = gate


def reset_tool_authz_gate() -> None:
    global _gate
    _gate = None


async def check_tool_permission(
    permission: Sequence[str] | None,
    user_id: str,
    tool_name: str,
) -> str | None:
    """None = allow; иначе сообщение об ошибке для агента."""
    if _gate is None:
        raise RuntimeError("tool authz gate is not bound")
    return await _gate(permission, user_id, tool_name)
