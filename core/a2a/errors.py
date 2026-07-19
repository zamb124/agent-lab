"""A2A Protocol 1.0 JSON-RPC application error codes (spec §5.4)."""

from __future__ import annotations

from enum import IntEnum


class A2AErrorCode(IntEnum):
    """Канонические коды ошибок A2A 1.0 (-32001..-32009)."""

    TASK_NOT_FOUND = -32001
    TASK_NOT_CANCELABLE = -32002
    PUSH_NOTIFICATION_NOT_SUPPORTED = -32003
    UNSUPPORTED_OPERATION = -32004
    CONTENT_TYPE_NOT_SUPPORTED = -32005
    INVALID_AGENT_RESPONSE = -32006
    EXTENDED_AGENT_CARD_NOT_CONFIGURED = -32007
    EXTENSION_SUPPORT_REQUIRED = -32008
    VERSION_NOT_SUPPORTED = -32009


A2A_ERROR_CODE_NAMES: dict[A2AErrorCode, str] = {
    A2AErrorCode.TASK_NOT_FOUND: "TaskNotFoundError",
    A2AErrorCode.TASK_NOT_CANCELABLE: "TaskNotCancelableError",
    A2AErrorCode.PUSH_NOTIFICATION_NOT_SUPPORTED: "PushNotificationNotSupportedError",
    A2AErrorCode.UNSUPPORTED_OPERATION: "UnsupportedOperationError",
    A2AErrorCode.CONTENT_TYPE_NOT_SUPPORTED: "ContentTypeNotSupportedError",
    A2AErrorCode.INVALID_AGENT_RESPONSE: "InvalidAgentResponseError",
    A2AErrorCode.EXTENDED_AGENT_CARD_NOT_CONFIGURED: "ExtendedAgentCardNotConfiguredError",
    A2AErrorCode.EXTENSION_SUPPORT_REQUIRED: "ExtensionSupportRequiredError",
    A2AErrorCode.VERSION_NOT_SUPPORTED: "VersionNotSupportedError",
}


class A2AApplicationError(Exception):
    """Доменная ошибка A2A → JSON-RPC application error (-32001..-32009)."""

    code: A2AErrorCode
    message: str

    def __init__(self, code: A2AErrorCode, message: str | None = None) -> None:
        self.code = code
        self.message = message if message is not None else A2A_ERROR_CODE_NAMES[code]
        super().__init__(self.message)

    def to_json_rpc_error(self) -> dict[str, int | str]:
        return {"code": int(self.code), "message": self.message}


__all__ = [
    "A2AErrorCode",
    "A2A_ERROR_CODE_NAMES",
    "A2AApplicationError",
]
