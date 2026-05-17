"""HTTP API capability-gateway."""

from fastapi import APIRouter

from apps.capability_gateway.dependencies import ContainerDep
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityCallResponse,
    CapabilityDocumentation,
    CapabilityLanguage,
    CapabilityManifest,
)

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
    return await container.capability_registry.call(request)
