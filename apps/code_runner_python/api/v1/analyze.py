"""HTTP API code-runner-python: статический контракт кода (reads/writes)."""

from fastapi import APIRouter

from apps.code_runner_python.dependencies import ContainerDep
from core.code_contract import (
    CodeContractAnalyzeRequest,
    CodeContractAnalyzeResponse,
    scan_code_contract,
)

router = APIRouter(prefix="/analyze", tags=["code-analysis"])


@router.post("", response_model=CodeContractAnalyzeResponse)
async def analyze_code(
    container: ContainerDep,
    request: CodeContractAnalyzeRequest,
) -> CodeContractAnalyzeResponse:
    _ = container
    contract = scan_code_contract(request.language, request.code)
    return CodeContractAnalyzeResponse(language=request.language, contract=contract)
