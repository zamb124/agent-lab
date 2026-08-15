"""HTTP/WS API language server session для code-runner-node."""

from fastapi import APIRouter, HTTPException, Response, WebSocket

from apps.code_runner_node.container import get_code_runner_node_container
from apps.code_runner_node.dependencies import ContainerDep
from core.capabilities.models import CodeLspSession, LspWorkspace

router = APIRouter(prefix="/lsp", tags=["code-lsp"])


@router.post("/session", response_model=CodeLspSession)
async def create_lsp_session(container: ContainerDep, workspace: LspWorkspace) -> CodeLspSession:
    return await container.lsp_manager.create(workspace)


@router.get("/session/{session_id}", status_code=204)
async def get_lsp_session(container: ContainerDep, session_id: str) -> Response:
    if not container.lsp_manager.exists(session_id):
        raise HTTPException(status_code=404, detail="language server session not found")
    return Response(status_code=204)


@router.delete("/session/{session_id}", status_code=204)
async def delete_lsp_session(container: ContainerDep, session_id: str) -> None:
    await container.lsp_manager.close(session_id)


@router.websocket("/ws/{session_id}")
async def lsp_websocket(websocket: WebSocket, session_id: str) -> None:
    container = get_code_runner_node_container()
    await container.lsp_manager.attach_websocket(websocket, session_id)
