"""
Унифицированные маршруты интеграций namespace: провайдер из path, логика из реестра коннекторов.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from apps.crm.api.tasks import _active_task_conflict, _to_response
from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import TaskResponse
from apps.crm.services.task_service import ActiveTaskExistsError
from core.context import get_context
from core.integrations.providers.amocrm import normalize_amocrm_subdomain_query

router = APIRouter(prefix="/namespaces", tags=["namespace-integrations"])


class AuthorizeResponse(BaseModel):
    authorize_url: str = Field(..., description="GET: открыть в браузере для OAuth")


class SyncStatsResponse(BaseModel):
    items: dict[str, int] = Field(default_factory=dict)


class IntegrationManifestItem(BaseModel):
    provider_id: str
    connected: bool
    display: str | None = None


class IntegrationsListResponse(BaseModel):
    items: list[IntegrationManifestItem]


def _auth_context_or_401():
    ctx = get_context()
    if ctx is None or ctx.user is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return ctx


def _resolve_subdomain(
    subdomain: str | None,
    amocrm_subdomain: str | None,
) -> str:
    raw = subdomain if isinstance(subdomain, str) and subdomain.strip() else None
    if raw is None and isinstance(amocrm_subdomain, str) and amocrm_subdomain.strip():
        raw = amocrm_subdomain.strip()
    if raw is None or not raw.strip():
        raise HTTPException(
            status_code=422,
            detail="Query subdomain обязателен (или устаревший amocrm_subdomain)",
        )
    try:
        return normalize_amocrm_subdomain_query(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/{namespace_name}/integrations",
    response_model=IntegrationsListResponse,
)
async def list_namespace_integrations(
    namespace_name: str,
    container: ContainerDep,
) -> IntegrationsListResponse:
    ctx = _auth_context_or_401()
    if not namespace_name.strip():
        raise HTTPException(status_code=422, detail="namespace_name required")
    ns_name = namespace_name.strip()
    existing = await container.namespace_repository.get(ns_name)
    if existing is None or existing.company_id != ctx.active_company.company_id:
        raise HTTPException(status_code=404, detail="namespace not found")
    crm = existing.crm_settings
    rows = await container.integration_registry.build_manifest(
        namespace_name=ns_name,
        company_id=ctx.active_company.company_id,
        user_id=ctx.user.user_id,
        crm_settings=crm,
    )
    items = [IntegrationManifestItem.model_validate(r) for r in rows]
    return IntegrationsListResponse(items=items)


@router.get(
    "/{namespace_name}/integrations/{provider}/authorize",
    response_model=AuthorizeResponse,
)
async def integration_authorize_url(
    namespace_name: str,
    provider: str,
    container: ContainerDep,
    subdomain: str | None = Query(
        default=None,
        min_length=1,
        description="Поддомен аккаунта (для amocrm — без .amocrm.ru)",
    ),
    amocrm_subdomain: str | None = Query(
        default=None,
        min_length=1,
        description="Устаревшее имя параметра; используйте subdomain",
    ),
    return_path: str = Query(
        default="/crm/spaces",
        description="Путь на платформе после OAuth (внутри origin)",
    ),
    return_origin: str | None = Query(
        default=None,
        description="Origin вкладки для редиректа после OAuth (тот же кластер, что platform_public_base_url)",
    ),
) -> AuthorizeResponse:
    if not return_path.startswith("/") or return_path.startswith("//"):
        raise HTTPException(status_code=422, detail="return_path must be a single-segment path")

    ctx = _auth_context_or_401()
    if not namespace_name.strip():
        raise HTTPException(status_code=422, detail="namespace_name required")
    sub = _resolve_subdomain(subdomain, amocrm_subdomain)
    try:
        connector = container.integration_registry.get(provider.strip())
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        ro = return_origin.strip() if isinstance(return_origin, str) and return_origin.strip() else None
        url = await connector.build_authorize_url(
            namespace_name=namespace_name.strip(),
            subdomain=sub,
            return_path=return_path,
            company_id=ctx.active_company.company_id,
            user_id=ctx.user.user_id,
            return_origin=ro,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AuthorizeResponse(authorize_url=url)


@router.post("/{namespace_name}/integrations/{provider}/sync")
async def integration_sync(
    namespace_name: str,
    provider: str,
    container: ContainerDep,
    response: Response,
) -> SyncStatsResponse | TaskResponse:
    _auth_context_or_401()
    if not namespace_name.strip():
        raise HTTPException(status_code=422, detail="namespace_name required")
    try:
        connector = container.integration_registry.get(provider.strip())
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ns = namespace_name.strip()
    if connector.entities_sync_runs_in_worker():
        try:
            row = await container.task_service.start_namespace_integration_job(
                namespace=ns,
                provider_id=provider.strip(),
                job="entities",
            )
        except ActiveTaskExistsError as exc:
            raise _active_task_conflict(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        response.status_code = 202
        return _to_response(row)
    try:
        stats = await connector.sync_entities(ns)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response.status_code = 200
    return SyncStatsResponse(items=stats)


@router.post("/{namespace_name}/integrations/{provider}/custom_fields/sync")
async def integration_custom_fields_sync(
    namespace_name: str,
    provider: str,
    container: ContainerDep,
    response: Response,
) -> SyncStatsResponse | TaskResponse:
    _auth_context_or_401()
    if not namespace_name.strip():
        raise HTTPException(status_code=422, detail="namespace_name required")
    try:
        connector = container.integration_registry.get(provider.strip())
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ns = namespace_name.strip()
    if connector.custom_fields_sync_runs_in_worker():
        try:
            row = await container.task_service.start_namespace_integration_job(
                namespace=ns,
                provider_id=provider.strip(),
                job="custom_fields",
            )
        except ActiveTaskExistsError as exc:
            raise _active_task_conflict(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        response.status_code = 202
        return _to_response(row)
    try:
        stats = await connector.sync_custom_field_catalog(ns)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response.status_code = 200
    return SyncStatsResponse(items=stats)
