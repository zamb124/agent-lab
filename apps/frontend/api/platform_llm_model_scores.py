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
    catalog_record_map,
    fetch_platform_free_model_records,
    provider_is_configured_for_free_pool,
    refresh_platform_free_models_cache,
    rescore_cached_platform_free_models,
)
from core.ai.models import AIModelRecord
from core.ai.providers import PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER, AICapability
from core.ai.scoring import (
    PlatformModelScoreHint,
    compute_platform_model_score,
    split_score_dimensions,
)
from core.config import get_settings
from core.db.models.platform import LLMModelScore
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.logging import get_logger
from core.models.identity_models import User
from core.types import JsonObject

logger = get_logger(__name__)
LLMModelScoreSource = Literal["config_seed", "manual", "benchmark_import", "computed"]

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
    editorial_prior: float = 0.0
    score_dimensions: dict[str, float] = Field(default_factory=dict)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    note: str | None = None
    updated_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    has_hint_row: bool = False


class LLMModelScoreListResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[LLMModelScoreDTO]


class LLMModelScoreUpsertRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)
    capability: AICapability
    enabled: bool = True
    editorial_prior: float = Field(default=0.0, ge=-50.0, le=50.0)
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


def _extract_breakdown(raw_dimensions: JsonObject | None) -> dict[str, float]:
    if raw_dimensions is None:
        return {}
    breakdown: dict[str, float] = {}
    for key, value in raw_dimensions.items():
        if not str(key).startswith("$breakdown_"):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            breakdown[str(key).removeprefix("$breakdown_")] = float(value)
    return breakdown


def _row_to_dto(row: LLMModelScore | None, *, computed: LLMModelScoreDTO) -> LLMModelScoreDTO:
    if row is None:
        return computed
    editorial_prior, hint_dimensions = split_score_dimensions(row.score_dimensions)
    source = _normalize_score_source(row.source)
    return LLMModelScoreDTO(
        provider=row.provider,
        model_id=row.model_id,
        capability=AICapability(row.capability),
        score=float(row.score),
        enabled=bool(row.enabled),
        source=source,
        editorial_prior=editorial_prior,
        score_dimensions=hint_dimensions,
        score_breakdown=_extract_breakdown(row.score_dimensions),
        note=row.note,
        updated_by_user_id=row.updated_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        has_hint_row=True,
    )


def _normalize_score_source(source: str) -> LLMModelScoreSource:
    if source == "config_seed":
        return "config_seed"
    if source == "benchmark_import":
        return "benchmark_import"
    if source == "computed":
        return "computed"
    return "manual"


async def _catalog_records_for_capability(
    container: ContainerDep,
    capability: AICapability,
) -> list[AIModelRecord]:
    settings = get_settings()
    records: list[AIModelRecord] = []
    for provider_slug in PLATFORM_FREE_MODEL_CANDIDATE_PROVIDER_ORDER:
        if not provider_is_configured_for_free_pool(settings, provider_slug):
            continue
        provider_records = await container.ai_model_catalog_repository.list_by_provider_capability(
            provider_slug,
            capability,
        )
        records.extend(provider_records)
    return records


async def _build_merged_score_items(container: ContainerDep) -> list[LLMModelScoreDTO]:
    settings = get_settings()
    capability = AICapability.LLM_CHAT
    catalog_records = await _catalog_records_for_capability(container, capability)
    catalog_by_key = catalog_record_map(catalog_records)
    hints = await container.llm_model_score_repository.list_hints(capability)
    db_rows = {
        (row.provider, row.model_id): row
        for row in await container.llm_model_score_repository.list_all()
        if row.capability == capability.value
    }

    pool_records = await fetch_platform_free_model_records(
        settings,
        container.ai_model_catalog_repository,
        model_score_provider=container.llm_model_score_repository,
    )
    seen: set[tuple[str, str]] = set()
    items: list[LLMModelScoreDTO] = []

    for pool_record in pool_records:
        key = (pool_record.provider, pool_record.id)
        seen.add(key)
        catalog_record = catalog_by_key.get(key)
        hint = hints.get(key)
        if catalog_record is None:
            continue
        computed = compute_platform_model_score(
            catalog_record,
            capability,
            hint=hint,
            scoring_config=settings.llm.model_scoring,
        )
        computed_dto = LLMModelScoreDTO(
            provider=pool_record.provider,
            model_id=pool_record.id,
            capability=capability,
            score=computed.score,
            enabled=hint.enabled if hint is not None else True,
            source="computed",
            editorial_prior=hint.editorial_prior if hint is not None else 0.0,
            score_dimensions=dict(hint.score_dimensions) if hint is not None else {},
            score_breakdown=computed.breakdown,
            note=hint.note if hint is not None else None,
            has_hint_row=hint is not None,
        )
        items.append(_row_to_dto(db_rows.get(key), computed=computed_dto))

    for key, row in db_rows.items():
        if key in seen:
            continue
        editorial_prior, hint_dimensions = split_score_dimensions(row.score_dimensions)
        catalog_record = catalog_by_key.get(key)
        if catalog_record is None:
            items.append(
                LLMModelScoreDTO(
                    provider=row.provider,
                    model_id=row.model_id,
                    capability=AICapability(row.capability),
                    score=float(row.score),
                    enabled=bool(row.enabled),
                    source=_normalize_score_source(row.source),
                    editorial_prior=editorial_prior,
                    score_dimensions=hint_dimensions,
                    score_breakdown=_extract_breakdown(row.score_dimensions),
                    note=row.note,
                    updated_by_user_id=row.updated_by_user_id,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    has_hint_row=True,
                )
            )
            continue
        hint = hints.get(key)
        computed = compute_platform_model_score(
            catalog_record,
            capability,
            hint=hint,
            scoring_config=settings.llm.model_scoring,
        )
        computed_dto = LLMModelScoreDTO(
            provider=row.provider,
            model_id=row.model_id,
            capability=capability,
            score=computed.score,
            enabled=bool(row.enabled),
            source=_normalize_score_source(row.source),
            editorial_prior=editorial_prior,
            score_dimensions=hint_dimensions,
            score_breakdown=computed.breakdown,
            note=row.note,
            updated_by_user_id=row.updated_by_user_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
            has_hint_row=True,
        )
        items.append(computed_dto)

    items.sort(key=lambda item: item.score, reverse=True)
    return items


async def _rescore_cache(container: ContainerDep) -> JsonObject:
    try:
        return await rescore_cached_platform_free_models(
            container.redis_client,
            get_settings(),
            container.ai_model_catalog_repository,
            model_score_provider=container.llm_model_score_repository,
        )
    except Exception as exc:  # pragma: no cover - defensive observability path
        logger.warning(
            "frontend.llm_model_scores_cache_rescore_failed",
            error=str(exc),
        )
        return {"cache_present": None, "count": None, "redis_ok": False}


async def _compute_score_for_hint(
    container: ContainerDep,
    *,
    provider: str,
    model_id: str,
    capability: AICapability,
    editorial_prior: float,
    score_dimensions: dict[str, float],
) -> tuple[float, dict[str, float]]:
    catalog_record = await container.ai_model_catalog_repository.get_provider_model(provider, model_id)
    if catalog_record is None:
        return 0.0, {}
    hint = PlatformModelScoreHint(
        editorial_prior=editorial_prior,
        score_dimensions=score_dimensions,
        enabled=True,
        source="manual",
        note=None,
    )
    computed = compute_platform_model_score(
        catalog_record,
        capability,
        hint=hint,
        scoring_config=get_settings().llm.model_scoring,
    )
    return computed.score, computed.breakdown


@router.get("", response_model=LLMModelScoreListResponse)
async def list_llm_model_scores(container: ContainerDep) -> LLMModelScoreListResponse:
    _ = _require_system_admin()
    return LLMModelScoreListResponse(items=await _build_merged_score_items(container))


@router.put("", response_model=LLMModelScoreMutationResponse)
async def upsert_llm_model_score(
    payload: LLMModelScoreUpsertRequest,
    container: ContainerDep,
) -> LLMModelScoreMutationResponse:
    user = _require_system_admin()
    computed_score, breakdown = await _compute_score_for_hint(
        container,
        provider=payload.provider,
        model_id=payload.model_id,
        capability=payload.capability,
        editorial_prior=payload.editorial_prior,
        score_dimensions=payload.score_dimensions,
    )
    result = await container.llm_model_score_repository.upsert_hints(
        provider=payload.provider,
        model_id=payload.model_id,
        capability=payload.capability,
        enabled=payload.enabled,
        source="manual",
        editorial_prior=payload.editorial_prior,
        score_dimensions=payload.score_dimensions,
        computed_score=computed_score,
        score_breakdown=breakdown,
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
    editorial_prior, hint_dimensions = split_score_dimensions(result.row.score_dimensions)
    item = LLMModelScoreDTO(
        provider=result.row.provider,
        model_id=result.row.model_id,
        capability=AICapability(result.row.capability),
        score=float(result.row.score),
        enabled=bool(result.row.enabled),
        source="manual",
        editorial_prior=editorial_prior,
        score_dimensions=hint_dimensions,
        score_breakdown=_extract_breakdown(result.row.score_dimensions) or breakdown,
        note=result.row.note,
        updated_by_user_id=result.row.updated_by_user_id,
        created_at=result.row.created_at,
        updated_at=result.row.updated_at,
        has_hint_row=True,
    )
    return LLMModelScoreMutationResponse(item=item, cache_rescore=cache_rescore)


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
