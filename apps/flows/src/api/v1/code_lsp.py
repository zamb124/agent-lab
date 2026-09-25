"""LSP bootstrap и WS JSON-RPC для code_node editor."""

from fastapi import APIRouter, HTTPException, WebSocket

from apps.flows.di import Di, FlowsDi
from core.capabilities import CodeLspSession, CodeLspSessionCreateRequest
from core.clients.service_client import ServiceClientError
from core.di import require_di

router = APIRouter(tags=["code-lsp"])


@router.post("/lsp/session", response_model=CodeLspSession)
async def create_code_lsp_session(
    request: CodeLspSessionCreateRequest,
    di: Di,
) -> CodeLspSession:
    try:
        return await di.code_lsp_service.create(request)
    except ServiceClientError as exc:
        status = exc.status_code if exc.status_code is not None else 502
        raise HTTPException(status_code=status, detail=exc.http_detail()) from exc


@router.websocket("/lsp/ws/{language}/{session_id}")
async def code_lsp_websocket(websocket: WebSocket, language: str, session_id: str) -> None:
    di = require_di(websocket, FlowsDi)
    await di.code_lsp_service.proxy_websocket(websocket, language, session_id)
