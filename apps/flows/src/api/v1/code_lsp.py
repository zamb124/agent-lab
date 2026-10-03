"""LSP bootstrap и WS JSON-RPC для code_node editor."""

from typing import NoReturn

from fastapi import APIRouter, WebSocket

from apps.flows.di import Di, FlowsDi
from core.capabilities import CodeLspSession, CodeLspSessionCreateRequest
from core.clients.service_client import ServiceClientError
from core.di import require_di
from core.types import JsonObject
from core.websocket import WsCommandError

router = APIRouter(tags=["code-lsp"])

_RUNNER_TRANSPORT: dict[int, tuple[str, str]] = {
    400: ("ws_invalid_payload", "ws_invalid_payload"),
    401: ("unauthorized", "unauthorized"),
    403: ("forbidden", "forbidden"),
    404: ("not_found", "not_found"),
    409: ("conflict", "conflict"),
    410: ("gone", "gone"),
    422: ("unprocessable", "ws_invalid_payload"),
    429: ("rate_limited", "rate_limited"),
    500: ("internal", "internal"),
    501: ("not_implemented", "unavailable"),
    502: ("upstream", "upstream"),
    503: ("unavailable", "unavailable"),
    504: ("gateway_timeout", "upstream"),
}


def _raise_runner_error(exc: ServiceClientError) -> NoReturn:
    status_code = exc.status_code if exc.status_code is not None else 502
    if status_code in _RUNNER_TRANSPORT:
        transport, error_code = _RUNNER_TRANSPORT[status_code]
    elif status_code >= 500:
        transport, error_code = "upstream", "upstream"
    else:
        transport, error_code = "ws_invalid_payload", "ws_invalid_payload"
    payload = exc.http_detail()
    error_params: JsonObject | None = None
    if isinstance(payload, dict):
        detail = "Language server session was rejected by the code runner"
        error_params = payload
    elif isinstance(payload, str) and payload != "":
        detail = payload
    else:
        detail = f"Language server session failed with HTTP {status_code}"
    raise WsCommandError(
        transport,
        detail,
        error_code=error_code,
        error_params=error_params,
    ) from exc


@router.post("/lsp/session", response_model=CodeLspSession)
async def create_code_lsp_session(
    request: CodeLspSessionCreateRequest,
    di: Di,
) -> CodeLspSession:
    try:
        return await di.code_lsp_service.create(request)
    except ServiceClientError as exc:
        _raise_runner_error(exc)


@router.websocket("/lsp/ws/{language}/{session_id}")
async def code_lsp_websocket(websocket: WebSocket, language: str, session_id: str) -> None:
    di = require_di(websocket, FlowsDi)
    await di.code_lsp_service.proxy_websocket(websocket, language, session_id)
