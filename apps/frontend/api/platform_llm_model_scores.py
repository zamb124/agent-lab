"""System-only API for platform LLM model scoring.

Routes:
    GET    /api/platform/llm-model-scores
    PUT    /api/platform/llm-model-scores
    DELETE /api/platform/llm-model-scores/{capability}/{provider}/{model_id:path}
    POST   /api/platform/llm-model-scores/refresh-cache
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.dependencies import ContainerDep, require_frontend_context
from core.ai.free_pool import (
    refresh_platform_free_models_cache,
    rescore_cached_platform_free_models,
)
from core.ai.providers import AICapability
from core.config import get_settings
from core.db.models.platform import LLMModelScore
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.models.identity_models import User
from core.types import JsonObject

logger = get_logger(__name__)
LLMModelScoreSource = Literal["config_seed", "manual", "benchmark_import"]

router = APIRouter(
    prefix="/api/platform/llm-model-scores",
    tags=["frontend", "platform", "llm-model-scores"],
)


class LLMModelScoreDTO(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str
    model_id: str
    capability: AICapability
    score: float
    enabled: bool
    source: LLMModelScoreSource
    score_dimensions: dict[str, float] = Field(default_factory=dict)
    note: str | None = None
    updated_by_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class LLMModelScoreListResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[LLMModelScoreDTO]


class LLMModelScoreUpsertRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)
    capability: AICapability
    score: float = Field(ge=0, le=1000)
    enabled: bool = True
    score_dimensions: dict[str, float] = Field(default_factory=dict)
    note: str | None = None


class LLMModelScoreMutationResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    item: LLMModelScoreDTO
    cache_rescore: JsonObject


class LLMModelScoreDeleteResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    deleted: bool
    cache_rescore: JsonObject


def _require_system_admin() -> User:
    context = require_frontend_context()
    company = context.active_company
    if company is None or company.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Доступно только для компании system")
    user = context.user
    roles = set(company.members.get(user.user_id, []) or [])
    roles.update(user.companies.get(SYSTEM_COMPANY_ID, []) or [])
    if "admin" in user.groups:
        roles.add("admin")
    if "admin" not in roles and "owner" not in roles:
        raise HTTPException(status_code=403, detail="Требуются права admin/owner в компании system")
    return user


def _row_to_dto(row: LLMModelScore) -> LLMModelScoreDTO:
    dimensions: dict[str, float] = {}
    for key, value in (row.score_dimensions or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            dimensions[str(key)] = float(value)
    source = _normalize_score_source(row.source)
    return LLMModelScoreDTO(
        provider=row.provider,
        model_id=row.model_id,
        capability=AICapability(row.capability),
        score=float(row.score),
        enabled=bool(row.enabled),
        source=source,
        score_dimensions=dimensions,
        note=row.note,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_score_source(source: str) -> LLMModelScoreSource:
    if source == "config_seed":
        return "config_seed"
    if source == "benchmark_import":
        return "benchmark_import"
    return "manual"


async def _rescore_cache(container: ContainerDep) -> JsonObject:
    try:
        return await rescore_cached_platform_free_models(
            container.redis_client,
            get_settings(),
            model_score_provider=container.llm_model_score_repository,
        )
    except Exception as exc:  # pragma: no cover - defensive observability path
        logger.warning(
            "frontend.llm_model_scores_cache_rescore_failed",
            error=str(exc),
        )
        return {"cache_present": None, "count": None, "redis_ok": False}


@router.get("", response_model=LLMModelScoreListResponse)
async def list_llm_model_scores(container: ContainerDep) -> LLMModelScoreListResponse:
    _ = _require_system_admin()
    rows = await container.llm_model_score_repository.list_all()
    return LLMModelScoreListResponse(items=[_row_to_dto(row) for row in rows])


@router.put("", response_model=LLMModelScoreMutationResponse)
async def upsert_llm_model_score(
    payload: LLMModelScoreUpsertRequest,
    container: ContainerDep,
) -> LLMModelScoreMutationResponse:
    user = _require_system_admin()
    result = await container.llm_model_score_repository.upsert(
        provider=payload.provider,
        model_id=payload.model_id,
        capability=payload.capability,
        score=payload.score,
        enabled=payload.enabled,
        source="manual",
        score_dimensions=payload.score_dimensions,
        note=payload.note,
        updated_by_user_id=user.user_id,
        overwrite=True,
    )
    cache_rescore = await _rescore_cache(container)
    logger.info(
        "frontend.llm_model_score_upserted",
        provider=result.row.provider,
        model_id=result.row.model_id,
        score=result.row.score,
        actor_user_id=user.user_id,
    )
    return LLMModelScoreMutationResponse(
        item=_row_to_dto(result.row),
        cache_rescore=cache_rescore,
    )


@router.delete("/{capability}/{provider}/{model_id:path}", response_model=LLMModelScoreDeleteResponse)
async def delete_llm_model_score(
    capability: AICapability,
    provider: str,
    model_id: str,
    container: ContainerDep,
) -> LLMModelScoreDeleteResponse:
    user = _require_system_admin()
    deleted = await container.llm_model_score_repository.delete(
        provider=provider,
        model_id=model_id,
        capability=capability,
    )
    cache_rescore = await _rescore_cache(container)
    logger.info(
        "frontend.llm_model_score_deleted",
        provider=provider,
        model_id=model_id,
        capability=capability.value,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return LLMModelScoreDeleteResponse(deleted=deleted, cache_rescore=cache_rescore)


@router.post("/refresh-cache")
async def refresh_llm_model_scores_cache(container: ContainerDep) -> JsonObject:
    user = _require_system_admin()
    result = await refresh_platform_free_models_cache(
        container.redis_client,
        get_settings(),
        container.ai_model_catalog_repository,
        model_score_provider=container.llm_model_score_repository,
    )
    logger.info(
        "frontend.llm_model_score_cache_refreshed",
        actor_user_id=user.user_id,
        count=result.get("count"),
        providers=result.get("providers"),
    )
    return result
