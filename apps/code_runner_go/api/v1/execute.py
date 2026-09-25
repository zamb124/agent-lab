"""HTTP API code-runner-go."""

import traceback

from fastapi import APIRouter

from apps.code_runner_go.di import Di
from apps.code_runner_go.services.executor import SERVICE_NAME
from core.capabilities import (
    CodeExecutionRequest,
    CodeExecutionResponse,
    code_execution_failed_response,
)

router = APIRouter(prefix="/execute", tags=["code-execution"])


@router.post("", response_model=CodeExecutionResponse)
async def execute_code(
    di: Di,
    request: CodeExecutionRequest,
) -> CodeExecutionResponse:
    try:
        return await di.executor.execute(request)
    except Exception as exc:
        return code_execution_failed_response(
            request,
            service=SERVICE_NAME,
            stage="service",
            message=str(exc),
            exception_type=type(exc).__name__,
            traceback_text="".join(traceback.format_exception(exc)),
        )
