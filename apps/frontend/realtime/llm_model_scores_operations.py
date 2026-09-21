"""Команды скоринга платформенных LLM (только компания system): overlay-оценки free pool, кеш, probe провайдеров."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from apps.frontend.container import FrontendContainer
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
    EDITORIAL_PRIOR_CAP,
    PlatformModelScoreOverlay,
    compute_platform_model_score,
)
from core.clients.llm.provider_runtime_status import (
    LLMModelRuntimeStatus,
    LLMProviderRuntimeStatus,
    collect_free_pool_runtime_status,
    probe_platform_free_providers,
)
from core.config import get_settings
from core.db.models.platform import LLMModelScore
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.request_scope import require_system_admin
from core.types import JsonObject
from core.websocket import EmptyPayload, raise_invalid

logger = get_logger(__name__)


class LLMModelScoreItem(LLMModelRuntimeStatus):
    capability: AICapability
    score: float
    enabled: bool
    editorial_prior: float = 0.0
    note: str | None = None
    has_overlay_row: bool = False
    intelligence_index: float | None = None
    coding_index: float | None = None
    agentic_index: float | None = None
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    updated_by_user_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class _ScoreCatalogRow:
    catalog_record: AIModelRecord
    overlay: PlatformModelScoreOverlay | None
    overlay_row: LLMModelScore | None


class LLMModelScoreListResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    items: list[LLMModelScoreItem]
    providers: list[LLMProviderRuntimeStatus]


class LLMModelScoreUpsertRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)
    capability: AICapability
    enabled: bool = True
    editorial_prior: float = Field(
        default=0.0,
        ge=-EDITORIAL_PRIOR_CAP,
        le=EDITORIAL_PRIOR_CAP,
    )
    note: str | None = None


class LLMModelScoreMutationResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    item: LLMModelScoreItem
    cache_rescore: JsonObject


class LLMModelScoreDeleteResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    deleted: bool
    cache_rescore: JsonObject


class LLMModelScoreDeletePayload(StrictBaseModel):
    capability: AICapability
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


def _item_from_catalog(
    catalog_record: AIModelRecord,
    *,
    overlay: PlatformModelScoreOverlay | None,
    overlay_row: LLMModelScore | None,
    runtime: LLMModelRuntimeStatus,
) -> LLMModelScoreItem:
    computed = compute_platform_model_score(
        catalog_record,
        AICapability.LLM_CHAT,
        overlay=overlay,
    )
    aa = catalog_record.artificial_analysis
    enabled = overlay.enabled if overlay is not None else True
    return LLMModelScoreItem(
        provider=runtime.provider,
        model_id=runtime.model_id,
        availability=runtime.availability,
        cooldown_seconds=runtime.cooldown_seconds,
        error_class=runtime.error_class,
        error_text=runtime.error_text,
        http_status=runtime.http_status,
        capability=AICapability.LLM_CHAT,
        score=computed.score,
        enabled=enabled,
        editorial_prior=overlay.editorial_prior if overlay is not None else 0.0,
        note=overlay.note if overlay is not None else None,
        has_overlay_row=overlay_row is not None,
        intelligence_index=aa.intelligence_index if aa is not None else None,
        coding_index=aa.coding_index if aa is not None else None,
        agentic_index=aa.agentic_index if aa is not None else None,
        score_breakdown=computed.breakdown,
        updated_by_user_id=overlay_row.updated_by_user_id if overlay_row is not None else None,
        created_at=overlay_row.created_at if overlay_row is not None else None,
        updated_at=overlay_row.updated_at if overlay_row is not None else None,
    )


async def _catalog_records_for_capability(
    container: FrontendContainer,
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


async def _build_score_catalog_rows(container: FrontendContainer) -> list[_ScoreCatalogRow]:
    settings = get_settings()
    capability = AICapability.LLM_CHAT
    catalog_records = await _catalog_records_for_capability(container, capability)
    catalog_by_key = catalog_record_map(catalog_records)
    overlays = await container.llm_model_score_repository.list_overlays(capability)
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
    rows: list[_ScoreCatalogRow] = []

    for pool_record in pool_records:
        key = (pool_record.provider, pool_record.id)
        seen.add(key)
        catalog_record = catalog_by_key.get(key)
        if catalog_record is None:
            raise ValueError(f"free-pool record {pool_record.provider}:{pool_record.id} is missing from the catalog")
        rows.append(
            _ScoreCatalogRow(
                catalog_record=catalog_record,
                overlay=overlays.get(key),
                overlay_row=db_rows.get(key),
            )
        )

    for key, row in db_rows.items():
        if key in seen:
            continue
        catalog_record = catalog_by_key.get(key)
        if catalog_record is None:
            continue
        rows.append(
            _ScoreCatalogRow(
                catalog_record=catalog_record,
                overlay=overlays.get(key),
                overlay_row=row,
            )
        )
    return rows


def _overlay_enabled(overlay: PlatformModelScoreOverlay | None) -> bool:
    if overlay is None:
        return True
    return overlay.enabled


async def _score_list_response(rows: list[_ScoreCatalogRow]) -> LLMModelScoreListResponse:
    status_by_key, providers = await collect_free_pool_runtime_status(
        [
            (
                row.catalog_record.provider,
                row.catalog_record.model_id,
                _overlay_enabled(row.overlay),
            )
            for row in rows
        ],
        settings=get_settings(),
    )
    items: list[LLMModelScoreItem] = []
    for row in rows:
        status = status_by_key.get((row.catalog_record.provider, row.catalog_record.model_id))
        if status is None:
            raise ValueError(
                f"runtime status is missing for {row.catalog_record.provider}:{row.catalog_record.model_id}"
            )
        items.append(
            _item_from_catalog(
                row.catalog_record,
                overlay=row.overlay,
                overlay_row=row.overlay_row,
                runtime=status,
            )
        )
    items.sort(key=lambda item: item.score, reverse=True)
    return LLMModelScoreListResponse(items=items, providers=providers)


async def _rescore_cache(container: FrontendContainer) -> JsonObject:
    return await rescore_cached_platform_free_models(
        container.redis_client,
        get_settings(),
        container.ai_model_catalog_repository,
        model_score_provider=container.llm_model_score_repository,
    )


async def op_llm_model_scores_list(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> LLMModelScoreListResponse:
    _ = payload, user
    _ = await require_system_admin(container.authz_service)
    return await _score_list_response(await _build_score_catalog_rows(container))


async def op_llm_model_scores_upsert(
    payload: LLMModelScoreUpsertRequest, *, user: User, container: FrontendContainer
) -> LLMModelScoreMutationResponse:
    _ = await require_system_admin(container.authz_service)
    catalog_record = await container.ai_model_catalog_repository.get_provider_model(
        payload.provider, payload.model_id
    )
    if catalog_record is None:
        raise_invalid(ValueError("model not found in catalog"))
    result = await container.llm_model_score_repository.upsert_overlay(
        provider=payload.provider,
        model_id=payload.model_id,
        capability=payload.capability,
        enabled=payload.enabled,
        editorial_prior=payload.editorial_prior,
        note=payload.note,
        updated_by_user_id=user.user_id,
    )
    cache_rescore = await _rescore_cache(container)
    overlay = PlatformModelScoreOverlay(
        enabled=bool(result.row.enabled),
        editorial_prior=float(result.row.editorial_prior),
        note=result.row.note,
    )
    status_by_key, _providers = await collect_free_pool_runtime_status(
        [(payload.provider, payload.model_id, payload.enabled)],
        settings=get_settings(),
    )
    runtime = status_by_key.get((payload.provider, payload.model_id))
    if runtime is None:
        raise ValueError(f"runtime status is missing for {payload.provider}:{payload.model_id}")
    item = _item_from_catalog(catalog_record, overlay=overlay, overlay_row=result.row, runtime=runtime)
    logger.info(
        "frontend.llm_model_score_upserted",
        provider=result.row.provider,
        model_id=result.row.model_id,
        score=item.score,
        actor_user_id=user.user_id,
    )
    return LLMModelScoreMutationResponse(item=item, cache_rescore=cache_rescore)


async def op_llm_model_scores_delete(
    payload: LLMModelScoreDeletePayload, *, user: User, container: FrontendContainer
) -> LLMModelScoreDeleteResponse:
    _ = await require_system_admin(container.authz_service)
    deleted = await container.llm_model_score_repository.delete(
        provider=payload.provider, model_id=payload.model_id, capability=payload.capability
    )
    cache_rescore = await _rescore_cache(container)
    logger.info(
        "frontend.llm_model_score_deleted",
        provider=payload.provider,
        model_id=payload.model_id,
        capability=AICapability(payload.capability).value,
        deleted=deleted,
        actor_user_id=user.user_id,
    )
    return LLMModelScoreDeleteResponse(deleted=deleted, cache_rescore=cache_rescore)


async def op_llm_model_scores_refresh_cache(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> JsonObject:
    _ = payload
    _ = await require_system_admin(container.authz_service)
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


async def op_llm_model_scores_probe_providers(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> LLMModelScoreListResponse:
    _ = payload
    _ = await require_system_admin(container.authz_service)
    snapshots = await probe_platform_free_providers(settings=get_settings())
    logger.info("frontend.llm_model_score_providers_probed", actor_user_id=user.user_id, count=len(snapshots))
    return await _score_list_response(await _build_score_catalog_rows(container))
