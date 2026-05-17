"""HTTP API code-runner-python validation."""

import traceback

from fastapi import APIRouter

from apps.code_runner_python.dependencies import ContainerDep
from apps.code_runner_python.services.executor import SERVICE_NAME
from core.capabilities import (
    CodeValidationRequest,
    CodeValidationResponse,
    code_validation_failed_response,
)

router = APIRouter(prefix="/validate", tags=["code-validation"])


@router.post("", response_model=CodeValidationResponse)
async def validate_code(
    container: ContainerDep,
    request: CodeValidationRequest,
) -> CodeValidationResponse:
    try:
        return await container.executor.validate(request)
    except Exception as exc:
        return code_validation_failed_response(
            request,
            service=SERVICE_NAME,
            stage="service",
            message=str(exc),
            exception_type=type(exc).__name__,
            traceback_text="".join(traceback.format_exception(exc)),
        )
