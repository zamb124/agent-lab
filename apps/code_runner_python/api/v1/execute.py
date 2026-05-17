"""HTTP API code-runner-python."""

import traceback

from fastapi import APIRouter

from apps.code_runner_python.dependencies import ContainerDep
from apps.code_runner_python.services.executor import SERVICE_NAME
from core.capabilities import (
    CodeExecutionRequest,
    CodeExecutionResponse,
    code_execution_failed_response,
)

router = APIRouter(prefix="/execute", tags=["code-execution"])


@router.post("", response_model=CodeExecutionResponse)
async def execute_code(
    container: ContainerDep,
    request: CodeExecutionRequest,
) -> CodeExecutionResponse:
    try:
        return await container.executor.execute(request)
    except Exception as exc:
        return code_execution_failed_response(
            request,
            service=SERVICE_NAME,
            stage="service",
            message=str(exc),
            exception_type=type(exc).__name__,
            traceback_text="".join(traceback.format_exception(exc)),
        )
