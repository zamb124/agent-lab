"""REST API for provider_litserve model registry management."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from huggingface_hub import scan_cache_dir, snapshot_download
from pydantic import BaseModel, Field

from apps.provider_litserve.config import get_provider_litserve_settings
from apps.provider_litserve.model_registry import (
    ModelKind,
    RegistryModel,
    create_or_replace_model,
    get_model,
    list_models,
    mark_model_deleted,
    mark_model_status,
)
from apps.provider_litserve.runtime_models import reload_runtime_catalog_from_sqlite
from core.utils.tokens import get_token_service

SYSTEM_COMPANY_ID = "system"

router = APIRouter(prefix="/api", tags=["litserve-models"])


class ProviderLitserveModelCreateRequest(BaseModel):
    kind: ModelKind = Field(description="embedding | rerank | stt | tts | vad")
    hf_model_id: str
    api_model_id: str


class ProviderLitserveModelListResponse(BaseModel):
    items: list[RegistryModel]


class ProviderLitserveModelDeleteResponse(BaseModel):
    model_id: str


def system_auth_dependency(request: Request) -> None:
    auth_header = request.headers.get("Authorization", "").strip()
    token = request.cookies.get("auth_token", "").strip()
    if auth_header:
        prefix = "Bearer "
        if not auth_header.startswith(prefix):
            raise HTTPException(status_code=401, detail="Invalid Authorization header")
        token = auth_header[len(prefix):].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    token_data = get_token_service().validate_token(token)
    if token_data is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    if token_data.company_id != SYSTEM_COMPANY_ID:
        raise HTTPException(status_code=403, detail="System company required")


_SYSTEM_AUTH_DEPENDENCY = [Depends(system_auth_dependency)]


def _reload_catalog() -> None:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    _ = reload_runtime_catalog_from_sqlite(cfg)


def _download_model_weights(model_id: str) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    model = get_model(cfg, model_id=model_id)
    mark_model_status(cfg, model_id=model_id, status="downloading")
    try:
        _ = snapshot_download(
            repo_id=model.hf_model_id,
            token=cfg.hf_token,
            local_files_only=False,
        )
    except Exception as exc:
        mark_model_status(cfg, model_id=model_id, status="failed", error=str(exc))
        raise
    mark_model_status(cfg, model_id=model_id, status="ready", error=None)
    _reload_catalog()


def _delete_model_weights(model_id: str) -> None:
    settings = get_provider_litserve_settings()
    cfg = settings.provider_litserve.infra
    model = get_model(cfg, model_id=model_id)
    try:
        cache_info = scan_cache_dir()
        strategy = cache_info.delete_revisions(model.hf_model_id)
        _ = strategy.execute()
    except Exception as exc:
        mark_model_status(cfg, model_id=model_id, status="failed", error=str(exc))
        raise
    mark_model_deleted(cfg, model_id=model_id)
    _reload_catalog()


@router.get(
    "/models",
    dependencies=_SYSTEM_AUTH_DEPENDENCY,
    response_model=ProviderLitserveModelListResponse,
)
def list_registry_models() -> ProviderLitserveModelListResponse:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    return ProviderLitserveModelListResponse(items=list_models(cfg))


@router.post(
    "/models",
    dependencies=_SYSTEM_AUTH_DEPENDENCY,
    response_model=RegistryModel,
)
def add_registry_model(
    payload: ProviderLitserveModelCreateRequest,
    background: BackgroundTasks,
) -> RegistryModel:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    model = create_or_replace_model(
        cfg,
        kind=payload.kind,
        hf_model_id=payload.hf_model_id,
        api_model_id=payload.api_model_id,
    )
    background.add_task(_download_model_weights, model.model_id)
    return model


@router.post(
    "/models/{model_id}/retry",
    dependencies=_SYSTEM_AUTH_DEPENDENCY,
    response_model=RegistryModel,
)
def retry_download(model_id: str, background: BackgroundTasks) -> RegistryModel:
    cfg = get_provider_litserve_settings().provider_litserve.infra
    mark_model_status(cfg, model_id=model_id, status="pending", error=None)
    background.add_task(_download_model_weights, model_id)
    return get_model(cfg, model_id=model_id)


@router.delete(
    "/models/{model_id}",
    dependencies=_SYSTEM_AUTH_DEPENDENCY,
    response_model=ProviderLitserveModelDeleteResponse,
)
def delete_registry_model(
    model_id: str,
    background: BackgroundTasks,
) -> ProviderLitserveModelDeleteResponse:
    background.add_task(_delete_model_weights, model_id)
    return ProviderLitserveModelDeleteResponse(model_id=model_id)
