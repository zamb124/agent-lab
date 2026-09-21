"""REST-зеркало команд `frontend/llm_model_scores/*` (только компания system)."""

from __future__ import annotations

from fastapi import APIRouter

from apps.frontend.dependencies import ContainerDep
from apps.frontend.realtime.llm_model_scores_operations import (
    LLMModelScoreDeletePayload,
    LLMModelScoreDeleteResponse,
    LLMModelScoreListResponse,
    LLMModelScoreMutationResponse,
    LLMModelScoreUpsertRequest,
    op_llm_model_scores_delete,
    op_llm_model_scores_list,
    op_llm_model_scores_probe_providers,
    op_llm_model_scores_refresh_cache,
    op_llm_model_scores_upsert,
)
from core.ai.providers import AICapability
from core.context import require_context
from core.types import JsonObject
from core.websocket import EmptyPayload

router = APIRouter(
    prefix="/api/platform/llm-model-scores",
    tags=["frontend", "platform", "llm-model-scores"],
)


@router.get("", response_model=LLMModelScoreListResponse)
async def list_llm_model_scores(container: ContainerDep) -> LLMModelScoreListResponse:
    return await op_llm_model_scores_list(EmptyPayload(), user=require_context().user, container=container)


@router.put("", response_model=LLMModelScoreMutationResponse)
async def upsert_llm_model_score(
    payload: LLMModelScoreUpsertRequest, container: ContainerDep
) -> LLMModelScoreMutationResponse:
    return await op_llm_model_scores_upsert(payload, user=require_context().user, container=container)


@router.delete("/{capability}/{provider}/{model_id:path}", response_model=LLMModelScoreDeleteResponse)
async def delete_llm_model_score(
    capability: AICapability, provider: str, model_id: str, container: ContainerDep
) -> LLMModelScoreDeleteResponse:
    return await op_llm_model_scores_delete(
        LLMModelScoreDeletePayload(capability=capability, provider=provider, model_id=model_id),
        user=require_context().user,
        container=container,
    )


@router.post("/refresh-cache")
async def refresh_llm_model_scores_cache(container: ContainerDep) -> JsonObject:
    return await op_llm_model_scores_refresh_cache(
        EmptyPayload(), user=require_context().user, container=container
    )


@router.post("/probe-providers", response_model=LLMModelScoreListResponse)
async def probe_llm_model_score_providers(container: ContainerDep) -> LLMModelScoreListResponse:
    return await op_llm_model_scores_probe_providers(
        EmptyPayload(), user=require_context().user, container=container
    )
