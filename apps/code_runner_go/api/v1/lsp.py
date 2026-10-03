"""HTTP/WS API language server session для code-runner-go."""

from fastapi import APIRouter, Response, WebSocket

from apps.code_runner_go.di import CodeRunnerGoDi, Di
from core.capabilities.models import CodeLspSession, LspWorkspace
from core.di import require_di
from core.websocket import WsCommandError

router = APIRouter(prefix="/lsp", tags=["code-lsp"])


@router.post("/session", response_model=CodeLspSession)
async def create_lsp_session(di: Di, workspace: LspWorkspace) -> CodeLspSession:
    return await di.lsp_manager.create(workspace)


@router.get("/session/{session_id}", status_code=204)
async def get_lsp_session(di: Di, session_id: str) -> Response:
    if not di.lsp_manager.exists(session_id):
        raise WsCommandError("not_found", "language server session not found", error_code="not_found")
    return Response(status_code=204)


@router.delete("/session/{session_id}", status_code=204)
async def delete_lsp_session(di: Di, session_id: str) -> None:
    await di.lsp_manager.close(session_id)


@router.websocket("/ws/{session_id}")
async def lsp_websocket(websocket: WebSocket, session_id: str) -> None:
    di = require_di(websocket, CodeRunnerGoDi)
    await di.lsp_manager.attach_websocket(websocket, session_id)
