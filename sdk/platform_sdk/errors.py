"""Ошибки CLI: один объект на stderr и стабильный код выхода."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from platform_sdk.json_types import JsonObject
from platform_sdk.wire import A2AErrorFrame, ErrorEnvelope

EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_AUTH = 4
EXIT_NOT_FOUND = 5
EXIT_CONFLICT = 6
EXIT_UNAVAILABLE = 7
EXIT_RUN_FAILED = 8
EXIT_INPUT_REQUIRED = 9
EXIT_EVAL_FAILED = 10

_STATUS_EXIT = {
    400: EXIT_INVALID,
    401: EXIT_AUTH,
    403: EXIT_AUTH,
    404: EXIT_NOT_FOUND,
    409: EXIT_CONFLICT,
    413: EXIT_INVALID,
    422: EXIT_INVALID,
    429: EXIT_UNAVAILABLE,
    500: EXIT_INTERNAL,
    501: EXIT_INTERNAL,
    502: EXIT_UNAVAILABLE,
    503: EXIT_UNAVAILABLE,
    504: EXIT_UNAVAILABLE,
}

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


class PlatformCliError(Exception):
    def __init__(
        self,
        *,
        error_code: str,
        error_detail: str,
        exit_code: int,
        http_status: int | None = None,
        error_params: JsonObject | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        service: str | None = None,
        retryable: bool = False,
        hint: str | None = None,
    ) -> None:
        super().__init__(error_detail)
        self.error_code = error_code
        self.error_detail = error_detail
        self.exit_code = exit_code
        self.http_status = http_status
        self.error_params = error_params if error_params is not None else {}
        self.request_id = request_id
        self.trace_id = trace_id
        self.service = service
        self.retryable = retryable
        self.hint = hint

    def payload(self) -> JsonObject:
        body: JsonObject = {
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "exit_code": self.exit_code,
            "retryable": self.retryable,
            "error_params": self.error_params,
        }
        if self.http_status is not None:
            body["http_status"] = self.http_status
        if self.request_id is not None:
            body["request_id"] = self.request_id
        if self.trace_id is not None:
            body["trace_id"] = self.trace_id
        if self.service is not None:
            body["service"] = self.service
        if self.hint is not None:
            body["hint"] = self.hint
        return body


def exit_for_status(status: int) -> int:
    return _STATUS_EXIT.get(status, EXIT_INTERNAL)


def retryable_status(status: int) -> bool:
    return status in _RETRYABLE_STATUS


def error_from_envelope(status: int, body: object) -> PlatformCliError:
    envelope = ErrorEnvelope.model_validate(body)
    code = envelope.resolved_code(status)
    return PlatformCliError(
        error_code=code,
        error_detail=envelope.resolved_detail(status),
        exit_code=exit_for_status(status),
        http_status=status,
        error_params=envelope.error_params,
        request_id=envelope.request_id,
        trace_id=envelope.trace_id,
        service=envelope.service,
        retryable=retryable_status(status),
        hint=_hint_for(code),
    )


def _hint_for(code: str) -> str | None:
    if code == "flow_version_conflict":
        return "platform pull, then retry push. --force-base overwrites the server version you just read."
    return None


def bundle_error(code: str, detail: str, *, path: str | None = None) -> PlatformCliError:
    params: JsonObject = {}
    if path is not None:
        params["path"] = path
    return PlatformCliError(
        error_code=code,
        error_detail=detail,
        exit_code=EXIT_USAGE,
        error_params=params,
    )


def usage_error(detail: str) -> PlatformCliError:
    return PlatformCliError(error_code="usage", error_detail=detail, exit_code=EXIT_USAGE)


def parse[ModelT: BaseModel](model: type[ModelT], value: object, label: str) -> ModelT:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        raise PlatformCliError(
            error_code="ws_invalid_payload",
            error_detail=f"{label}: {exc}",
            exit_code=EXIT_INVALID,
        ) from exc


def a2a_error(body: object) -> PlatformCliError:
    try:
        frame = A2AErrorFrame.model_validate(body)
    except ValidationError:
        return PlatformCliError(
            error_code="a2a_error",
            error_detail="A2A response has no error object",
            exit_code=EXIT_INTERNAL,
        )
    detail = frame.error.message if frame.error.message != "" else "A2A request failed"
    error_code = f"a2a_{frame.error.code}" if frame.error.code is not None else "a2a_error"
    return PlatformCliError(
        error_code=error_code,
        error_detail=detail,
        exit_code=EXIT_INTERNAL,
        error_params={"data": frame.error.data} if frame.error.data else {},
    )
