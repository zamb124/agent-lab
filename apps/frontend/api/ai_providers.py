"""REST-зеркало команд `frontend/ai_providers/*` (AI-провайдеры компании, admin)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from apps.frontend.di import Di
from apps.frontend.models import (
    AIProvidersCapabilityUpdate,
    CustomProviderCreate,
    CustomProviderUpdate,
)
from apps.frontend.realtime.ai_providers_operations import (
    AIProvidersCapabilityIdPayload,
    AIProvidersCapabilityPayload,
    AIProvidersMutationResult,
    AIProvidersSnapshotPayload,
    CustomProviderCreated,
    CustomProviderIdPayload,
    CustomProviderUpdatePayload,
    op_ai_providers_capability_remove,
    op_ai_providers_capability_update,
    op_ai_providers_custom_create,
    op_ai_providers_custom_remove,
    op_ai_providers_custom_update,
    op_ai_providers_llm_context_remove,
    op_ai_providers_llm_context_update,
    op_ai_providers_resolved,
    op_ai_providers_snapshot,
)
from core.context import require_context
from core.llm_context import LLMContextPatch
from core.types import JsonObject
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/settings/ai-providers", tags=["settings", "ai-providers"])


@router.get("")
async def get_ai_providers(request: Request, di: Di) -> JsonObject:
    return await op_ai_providers_snapshot(
        AIProvidersSnapshotPayload(public_host=request.headers.get("host")),
        user=require_context().user,
        di=di,
    )


@router.put("/llm-context", response_model=AIProvidersMutationResult)
async def put_llm_context(payload: LLMContextPatch, di: Di) -> AIProvidersMutationResult:
    return await op_ai_providers_llm_context_update(payload, user=require_context().user, di=di)


@router.delete("/llm-context", response_model=AIProvidersMutationResult)
async def delete_llm_context(di: Di) -> AIProvidersMutationResult:
    return await op_ai_providers_llm_context_remove(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.put("/{capability}", response_model=AIProvidersMutationResult)
async def put_capability(
    capability: str, payload: AIProvidersCapabilityUpdate, di: Di
) -> AIProvidersMutationResult:
    return await op_ai_providers_capability_update(
        AIProvidersCapabilityPayload.model_validate({"capability": capability, **payload.model_dump()}),
        user=require_context().user,
        di=di,
    )


@router.delete("/{capability}", response_model=AIProvidersMutationResult)
async def delete_capability(capability: str, di: Di) -> AIProvidersMutationResult:
    return await op_ai_providers_capability_remove(
        AIProvidersCapabilityIdPayload(capability=capability), user=require_context().user, di=di
    )


@router.post("/custom", response_model=CustomProviderCreated)
async def create_custom_provider(payload: CustomProviderCreate, di: Di) -> CustomProviderCreated:
    return await op_ai_providers_custom_create(payload, user=require_context().user, di=di)


@router.patch("/custom/{provider_id}", response_model=AIProvidersMutationResult)
async def update_custom_provider(
    provider_id: str, payload: CustomProviderUpdate, di: Di
) -> AIProvidersMutationResult:
    return await op_ai_providers_custom_update(
        CustomProviderUpdatePayload.model_validate({"provider_id": provider_id, **payload.model_dump()}),
        user=require_context().user,
        di=di,
    )


@router.delete("/custom/{provider_id}", response_model=AIProvidersMutationResult)
async def delete_custom_provider(provider_id: str, di: Di) -> AIProvidersMutationResult:
    return await op_ai_providers_custom_remove(
        CustomProviderIdPayload(provider_id=provider_id), user=require_context().user, di=di
    )


@router.get("/resolved")
async def get_resolved(di: Di) -> JsonObject:
    return await op_ai_providers_resolved(EmptyPayload(), user=require_context().user, di=di)
