"""HTTP API capability-gateway."""

from fastapi import APIRouter

from apps.capability_gateway.di import Di
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityCallResponse,
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilityManifest,
)
from core.clients.service_client import ServiceClientError
from core.types import JsonObject
from core.websocket import WsCommandError

router = APIRouter(prefix="/capabilities", tags=["capabilities"])

_PEER_CLIENT_TRANSPORT: dict[int, tuple[str, str]] = {
    400: ("ws_invalid_payload", "ws_invalid_payload"),
    401: ("unauthorized", "unauthorized"),
    403: ("forbidden", "forbidden"),
    404: ("not_found", "not_found"),
    409: ("conflict", "conflict"),
    410: ("gone", "gone"),
    422: ("unprocessable", "ws_invalid_payload"),
    429: ("rate_limited", "rate_limited"),
}


def _raise_peer_client_error(exc: ServiceClientError, status_code: int) -> None:
    transport, error_code = _PEER_CLIENT_TRANSPORT.get(
        status_code,
        ("ws_invalid_payload", "ws_invalid_payload"),
    )
    payload = exc.http_detail()
    error_params: JsonObject | None = None
    if isinstance(payload, dict):
        detail = "Capability call was rejected by the peer service"
        error_params = payload
    elif isinstance(payload, str) and payload != "":
        detail = payload
    else:
        detail = f"Capability call was rejected with HTTP {status_code}"
    raise WsCommandError(
        transport,
        detail,
        error_code=error_code,
        error_params=error_params,
    ) from exc


@router.get("/manifest", response_model=CapabilityManifest)
async def get_manifest(di: Di) -> CapabilityManifest:
    return await di.capability_registry.manifest()


@router.get("/documentation", response_model=CapabilityDocumentation)
async def get_documentation(
    di: Di,
    language: CapabilityLanguage | None = None,
) -> CapabilityDocumentation:
    return await di.capability_registry.documentation(language=language)


@router.post("/call", response_model=CapabilityCallResponse)
async def call_capability(
    di: Di,
    request: CapabilityCallRequest,
) -> CapabilityCallResponse:
    try:
        return await di.capability_registry.call(request)
    except ServiceClientError as exc:
        # 4xx peer (например tool-runtime 422) — не маскировать под 500 gateway.
        status_code = exc.status_code
        if status_code is not None and 400 <= status_code < 500:
            _raise_peer_client_error(exc, status_code)
        raise
