"""
WebSocket-инфраструктура платформы.

Один сокет `/<svc>/api/ws/notifications` несёт два потока:

1. push (server → client) — UIEvent-фреймы из Redis-канала `platform:ui_events`,
   публикация через `core/ui_events/dispatcher.py`.
2. RPC request-reply (client → server → client) — фреймы
   `{ request_id, type: <...>_requested, payload }`, обрабатываются
   command-handler'ами, зарегистрированными через
   `register_ws_command_handler` в `core.websocket.command_router`.
"""

from core.websocket.command_router import (
    CommandHandler,
    WsCommandError,
    derive_failed_type,
    derive_succeeded_type,
    dispatch_ws_command,
    dump_ws_result,
    has_ws_command_handler,
    list_ws_command_types,
    register_ws_command_handler,
    validate_ws_payload,
)
from core.websocket.manager import NotificationManager, notification_manager

__all__ = [
    "NotificationManager",
    "CommandHandler",
    "WsCommandError",
    "derive_failed_type",
    "derive_succeeded_type",
    "dispatch_ws_command",
    "dump_ws_result",
    "has_ws_command_handler",
    "list_ws_command_types",
    "notification_manager",
    "register_ws_command_handler",
    "validate_ws_payload",
]
