"""Bootstrap LSP-сессии code_node: stubs → runner language server → public WS path."""

from __future__ import annotations

from typing import final

from fastapi import WebSocket

from core.capabilities import (
    CapabilityLanguage,
    CodeLspSession,
    CodeLspSessionCreateRequest,
    build_lsp_workspace,
)
from core.clients.capability_gateway_client import CapabilityGatewayClient
from core.clients.service_client import ServiceClient, ServiceClientError
from core.clients.service_websocket import proxy_service_websocket
from core.logging import get_logger
from core.websocket.auth import get_user_from_websocket

logger = get_logger(__name__)

RUNNER_LSP_PREFIXES: dict[CapabilityLanguage, tuple[str, str]] = {
    "python": ("code_runner_python", "/code-runner-python/api/v1/lsp"),
    "javascript": ("code_runner_node", "/code-runner-node/api/v1/lsp"),
    "typescript": ("code_runner_node", "/code-runner-node/api/v1/lsp"),
    "go": ("code_runner_go", "/code-runner-go/api/v1/lsp"),
    "csharp": ("code_runner_csharp", "/code-runner-csharp/api/v1/lsp"),
}

_PUBLIC_WS_PREFIX = "/flows/api/v1/code/lsp/ws"


@final
class CodeLspService:
    """Оркестрация LSP: documentation → workspace stubs → runner session → WS proxy."""

    def __init__(self, service_client: ServiceClient) -> None:
        self._http = service_client
        self._gateway = CapabilityGatewayClient(service_client)

    async def create(self, request: CodeLspSessionCreateRequest) -> CodeLspSession:
        documentation = await self._gateway.get_documentation(request.language)
        workspace = build_lsp_workspace(documentation, request)
        service, prefix = RUNNER_LSP_PREFIXES[request.language]
        raw = await self._http.post(
            service,
            f"{prefix}/session",
            json=workspace.model_dump(mode="json"),
            timeout=60.0,
        )
        session = CodeLspSession.model_validate(raw)
        public = session.model_copy(
            update={"ws_path": f"{_PUBLIC_WS_PREFIX}/{request.language}/{session.session_id}"}
        )
        logger.info(
            "code_lsp.session_created",
            session_id=session.session_id,
            language=request.language,
            service=service,
        )
        return public

    async def proxy_websocket(self, websocket: WebSocket, language: str, session_id: str) -> None:
        user = await get_user_from_websocket(websocket)
        runner = _runner_prefix(language)
        if user is None or runner is None:
            await websocket.accept()
            await websocket.close(code=1008)
            return
        service, prefix = runner
        try:
            _ = await self._http.get(service, f"{prefix}/session/{session_id}", timeout=10.0)
        except ServiceClientError as exc:
            await websocket.accept()
            if exc.status_code == 404:
                await websocket.close(code=1008)
                return
            await websocket.close(code=1011)
            raise
        await proxy_service_websocket(websocket, service, f"{prefix}/ws/{session_id}")


def _runner_prefix(language: str) -> tuple[str, str] | None:
    for key, value in RUNNER_LSP_PREFIXES.items():
        if key == language:
            return value
    return None
