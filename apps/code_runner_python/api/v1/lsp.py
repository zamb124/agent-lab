"""HTTP/WS API language server session для code-runner-python."""

from fastapi import APIRouter, HTTPException, Response, WebSocket

from apps.code_runner_python.di import CodeRunnerPythonDi, Di
from core.capabilities.models import CodeLspSession, LspWorkspace
from core.di import require_di

router = APIRouter(prefix="/lsp", tags=["code-lsp"])


@router.post("/session", response_model=CodeLspSession)
async def create_lsp_session(di: Di, workspace: LspWorkspace) -> CodeLspSession:
    return await di.lsp_manager.create(workspace)


@router.get("/session/{session_id}", status_code=204)
async def get_lsp_session(di: Di, session_id: str) -> Response:
    if not di.lsp_manager.exists(session_id):
        raise HTTPException(status_code=404, detail="language server session not found")
    return Response(status_code=204)


@router.delete("/session/{session_id}", status_code=204)
async def delete_lsp_session(di: Di, session_id: str) -> None:
    await di.lsp_manager.close(session_id)


@router.websocket("/ws/{session_id}")
async def lsp_websocket(websocket: WebSocket, session_id: str) -> None:
    di = require_di(websocket, CodeRunnerPythonDi)
    await di.lsp_manager.attach_websocket(websocket, session_id)
