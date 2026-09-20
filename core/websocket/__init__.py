"""
Каталог `op_*` для bus `realtime`.

Команды приходят как `PlatformEvent` (`…/_requested`) через
`POST /{svc}/api/internal/realtime/command`. Push и исход — тот же
`PlatformEvent` в Centrifugo (`/realtime`).
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
from core.websocket.operation import (
    Operation,
    RegisteredOperation,
    raise_conflict,
    raise_forbidden,
    raise_internal,
    raise_invalid,
    raise_not_found,
    raise_unavailable,
    raise_upstream,
    register_service_operations,
    ws_command_error_status,
)

__all__ = [
    "CommandHandler",
    "Operation",
    "RegisteredOperation",
    "WsCommandError",
    "derive_failed_type",
    "derive_succeeded_type",
    "dispatch_ws_command",
    "dump_ws_result",
    "has_ws_command_handler",
    "list_ws_command_types",
    "raise_conflict",
    "raise_forbidden",
    "raise_internal",
    "raise_invalid",
    "raise_not_found",
    "raise_unavailable",
    "raise_upstream",
    "register_service_operations",
    "register_ws_command_handler",
    "validate_ws_payload",
    "ws_command_error_status",
]
