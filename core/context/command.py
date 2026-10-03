"""Контекст исполняемой realtime-команды.

``command_event_id`` — ``event_id`` входящего ``PlatformEvent``, который
``execute_realtime_command`` ставит на время ``dispatch_ws_command``. ``op_*``
и сервисы читают его как causation-id исходящих событий и как ключ
идемпотентности по умолчанию для команд с эффектом в леджере.
"""

from __future__ import annotations

import contextvars

_command_event_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "command_event_id", default=None
)


def current_command_event_id() -> str | None:
    """``event_id`` исполняемой WS-команды; вне команды — ``None``."""
    return _command_event_id.get()


def set_command_event_id(event_id: str) -> contextvars.Token[str | None]:
    return _command_event_id.set(event_id)


def reset_command_event_id(token: contextvars.Token[str | None]) -> None:
    _command_event_id.reset(token)
