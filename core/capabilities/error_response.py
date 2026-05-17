"""Helpers for language-neutral code execution error envelopes."""

from __future__ import annotations

from core.capabilities.models import (
    CodeExecutionErrorEnvelope,
    CodeExecutionRequest,
    CodeExecutionResponse,
)


def code_execution_failed_response(
    request: CodeExecutionRequest,
    *,
    service: str,
    stage: str,
    message: str,
    exception_type: str,
    traceback_text: str | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
) -> CodeExecutionResponse:
    """Build a failed CodeExecutionResponse preserving correlation fields."""
    return CodeExecutionResponse(
        status="failed",
        state=request.state,
        error=CodeExecutionErrorEnvelope(
            language=request.language,
            service=service,
            stage=stage,
            message=message,
            exception_type=exception_type,
            traceback=traceback_text,
            stdout=stdout,
            stderr=stderr,
            request_id=request.context.request_id,
            trace_id=request.context.trace_id,
        ),
    )
