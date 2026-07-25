"""HTTP API capability-gateway."""

from fastapi import APIRouter, HTTPException

from apps.capability_gateway.dependencies import ContainerDep
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityCallResponse,
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilityManifest,
)
from core.clients.service_client import ServiceClientError

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("/manifest", response_model=CapabilityManifest)
async def get_manifest(container: ContainerDep) -> CapabilityManifest:
    return await container.capability_registry.manifest()


@router.get("/documentation", response_model=CapabilityDocumentation)
async def get_documentation(
    container: ContainerDep,
    language: CapabilityLanguage | None = None,
) -> CapabilityDocumentation:
    return await container.capability_registry.documentation(language=language)


@router.post("/call", response_model=CapabilityCallResponse)
async def call_capability(
    container: ContainerDep,
    request: CapabilityCallRequest,
) -> CapabilityCallResponse:
    try:
        return await container.capability_registry.call(request)
    except ServiceClientError as exc:
        # 4xx peer (например tool-runtime 422) — не маскировать под 500 gateway.
        status_code = exc.status_code
        if status_code is not None and 400 <= status_code < 500:
            raise HTTPException(status_code=status_code, detail=exc.http_detail()) from exc
        raise
