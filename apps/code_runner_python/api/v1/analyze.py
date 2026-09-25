"""HTTP API code-runner-python: статический контракт кода (reads/writes)."""

from fastapi import APIRouter

from core.code_contract import (
    CodeContractAnalyzeRequest,
    CodeContractAnalyzeResponse,
    scan_code_contract,
)

router = APIRouter(prefix="/analyze", tags=["code-analysis"])


@router.post("", response_model=CodeContractAnalyzeResponse)
async def analyze_code(
    request: CodeContractAnalyzeRequest,
) -> CodeContractAnalyzeResponse:
    contract = scan_code_contract(request.language, request.code)
    return CodeContractAnalyzeResponse(language=request.language, contract=contract)
