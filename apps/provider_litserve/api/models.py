"""REST API каталога моделей provider_litserve (админка ``/litserve``).

Источник истины — таблица ``provider_litserve_models`` (Postgres shared).
Хендлеры только меняют желаемое состояние: ``pending`` — очередь на скачивание
весов, ``deleting`` — очередь на очистку кэша; физическую работу выполняет
ops-цикл пода (``apps.provider_litserve.model_ops``), не request-scope задачи.

Авторизация — канонический ``require_system_admin`` (компания ``system`` +
``company#admin``), без сервис-специфичного парсинга токенов.
"""

from __future__ import annotations

from typing import ClassVar

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from apps.provider_litserve.di import Di
from core.models.provider_litserve_model import (
    LitserveModelKind,
    ProviderLitserveModel,
    build_litserve_entry,
)
from core.request_scope import require_system_admin
from core.types import JsonObject
from core.websocket import raise_invalid, raise_not_found

router = APIRouter(prefix="/api", tags=["litserve-models"])


class ProviderLitserveModelCreateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    kind: LitserveModelKind = Field(description="embedding | rerank | stt | tts | vad")
    hf_model_id: str
    api_model_id: str
    params: JsonObject = Field(
        default_factory=dict,
        description=(
            "Поля записи каталога сверх api/hf id (backend, revision, voice, "
            "synthesis_locale, instruct, sample_rate, threshold, dimension, …). "
            "Валидируются entry-моделью kind."
        ),
    )


class ProviderLitserveModelItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    model_id: str
    kind: str
    hf_model_id: str
    api_model_id: str
    status: str
    error: str | None
    params: JsonObject
    created_at: str
    updated_at: str


class ProviderLitserveModelListResponse(BaseModel):
    items: list[ProviderLitserveModelItem]


class ProviderLitserveModelDeleteResponse(BaseModel):
    model_id: str


def _row_to_item(row: ProviderLitserveModel) -> ProviderLitserveModelItem:
    return ProviderLitserveModelItem(
        model_id=row.model_id,
        kind=row.kind,
        hf_model_id=row.hf_model_id,
        api_model_id=row.api_model_id,
        status=row.status,
        error=row.error,
        params=row.params,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/models", response_model=ProviderLitserveModelListResponse)
async def list_registry_models(di: Di) -> ProviderLitserveModelListResponse:
    _ = await require_system_admin(di.authz_service)
    rows = await ProviderLitserveModel.list_by_created_at_desc()
    return ProviderLitserveModelListResponse(items=[_row_to_item(row) for row in rows])


@router.post("/models", response_model=ProviderLitserveModelItem)
async def add_registry_model(
    payload: ProviderLitserveModelCreateRequest,
    di: Di,
) -> ProviderLitserveModelItem:
    _ = await require_system_admin(di.authz_service)
    try:
        entry = build_litserve_entry(
            kind=payload.kind,
            api_model_id=payload.api_model_id,
            hf_model_id=payload.hf_model_id,
            params=payload.params,
        )
    except ValueError as exc:
        raise_invalid(exc)
    row = await ProviderLitserveModel.create_or_replace(kind=payload.kind, entry=entry)
    return _row_to_item(row)


@router.post("/models/{model_id}/retry", response_model=ProviderLitserveModelItem)
async def retry_download(model_id: str, di: Di) -> ProviderLitserveModelItem:
    _ = await require_system_admin(di.authz_service)
    row = await ProviderLitserveModel.get(model_id)
    if row is None or row.status == "deleted":
        raise_not_found(ValueError(f"provider_litserve model not found: {model_id}"))
    if row.status == "deleting":
        raise_invalid(ValueError(f"provider_litserve model is being deleted: {model_id}"))
    row = await ProviderLitserveModel.mark_status(
        model_id=model_id,
        status="pending",
        error=None,
    )
    return _row_to_item(row)


@router.delete("/models/{model_id}", response_model=ProviderLitserveModelDeleteResponse)
async def delete_registry_model(
    model_id: str,
    di: Di,
) -> ProviderLitserveModelDeleteResponse:
    _ = await require_system_admin(di.authz_service)
    row = await ProviderLitserveModel.get(model_id)
    if row is None or row.status == "deleted":
        raise_not_found(ValueError(f"provider_litserve model not found: {model_id}"))
    if row.status != "deleting":
        _ = await ProviderLitserveModel.mark_status(model_id=model_id, status="deleting")
    return ProviderLitserveModelDeleteResponse(model_id=model_id)
