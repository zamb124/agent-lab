"""
Унифицированные маршруты интеграций namespace: провайдер из path, логика из реестра коннекторов.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from apps.crm.api.tasks import _active_task_conflict, _to_response
from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import TaskResponse
from apps.crm.services.task_service import ActiveTaskExistsError
from core.api.integration_oauth_error_html import resolve_oauth_integration_locale
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
    auto_sync_enabled: bool | None = None
    auto_sync_cron: str | None = None
    auto_sync_timezone: str | None = None
    auto_sync_schedule_task_id: str | None = None
    auto_note_ai_analyze: bool | None = None


class AutoNoteAiAnalyzeUpdateRequest(BaseModel):
    auto_note_ai_analyze: bool = Field(
        ...,
        description="Для новых заметок из интеграции автоматически ставить задачу AI-анализа",
    )


class IntegrationAutoSyncUpdateRequest(BaseModel):
    auto_sync_enabled: bool = Field(..., description="Включить периодический unified-синк")
    auto_sync_cron: str | None = Field(
        default=None,
        description="Cron (5 полей), обязателен при auto_sync_enabled=true",
    )
    auto_sync_timezone: str | None = Field(
        default="UTC",
        description="IANA timezone для интерпретации cron",
    )


class IntegrationsListResponse(BaseModel):
    items: list[IntegrationManifestItem]


@dataclass(frozen=True)
class _AuthenticatedContext:
    user_id: str
    company_id: str


def _auth_context_or_401() -> _AuthenticatedContext:
    ctx = get_context()
    if ctx is None or ctx.user is None or ctx.active_company is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return _AuthenticatedContext(
        user_id=ctx.user.user_id,
        company_id=ctx.active_company.company_id,
    )


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
    if existing is None or existing.company_id != ctx.company_id:
        raise HTTPException(status_code=404, detail="namespace not found")
    crm = existing.crm_settings
    rows = await container.integration_registry.build_manifest(
        namespace_name=ns_name,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        crm_settings=crm,
    )
    items = [IntegrationManifestItem.model_validate(r) for r in rows]
    return IntegrationsListResponse(items=items)


@router.get(
    "/{namespace_name}/integrations/{provider}/authorize",
    response_model=AuthorizeResponse,
)
async def integration_authorize_url(
    request: Request,
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
        oauth_ui_locale = resolve_oauth_integration_locale(
            request.headers.get("accept-language"),
            language_cookie=request.cookies.get("language"),
        )
        url = await connector.build_authorize_url(
            namespace_name=namespace_name.strip(),
            subdomain=sub,
            return_path=return_path,
            company_id=ctx.company_id,
            user_id=ctx.user_id,
            return_origin=ro,
            oauth_ui_locale=oauth_ui_locale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return AuthorizeResponse(authorize_url=url)


@router.patch(
    "/{namespace_name}/integrations/{provider}/auto-sync",
    response_model=IntegrationManifestItem,
)
async def integration_auto_sync_patch(
    namespace_name: str,
    provider: str,
    body: IntegrationAutoSyncUpdateRequest,
    container: ContainerDep,
) -> IntegrationManifestItem:
    ctx = _auth_context_or_401()
    if not namespace_name.strip():
        raise HTTPException(status_code=422, detail="namespace_name required")
    try:
        connector = container.integration_registry.get(provider.strip())
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ns_name = namespace_name.strip()
    existing_ns = await container.namespace_repository.get(ns_name)
    if existing_ns is None or existing_ns.company_id != ctx.company_id:
        raise HTTPException(status_code=404, detail="namespace not found")
    try:
        await container.integration_auto_sync_service.apply_integration_auto_sync(
            company_id=ctx.company_id,
            acting_user_id=ctx.user_id,
            namespace_name=ns_name,
            provider_id=provider.strip(),
            auto_sync_enabled=body.auto_sync_enabled,
            auto_sync_cron=body.auto_sync_cron,
            auto_sync_timezone=body.auto_sync_timezone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    refreshed = await container.namespace_repository.get(ns_name)
    crm = refreshed.crm_settings if refreshed is not None else None
    row = await connector.manifest_item(
        namespace_name=ns_name,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        crm_settings=crm,
    )
    return IntegrationManifestItem.model_validate(row)


@router.patch(
    "/{namespace_name}/integrations/{provider}/auto-note-ai-analyze",
    response_model=IntegrationManifestItem,
)
async def integration_auto_note_ai_analyze_patch(
    namespace_name: str,
    provider: str,
    body: AutoNoteAiAnalyzeUpdateRequest,
    container: ContainerDep,
) -> IntegrationManifestItem:
    ctx = _auth_context_or_401()
    if not namespace_name.strip():
        raise HTTPException(status_code=422, detail="namespace_name required")
    try:
        connector = container.integration_registry.get(provider.strip())
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ns_name = namespace_name.strip()
    existing_ns = await container.namespace_repository.get(ns_name)
    if existing_ns is None or existing_ns.company_id != ctx.company_id:
        raise HTTPException(status_code=404, detail="namespace not found")
    try:
        await container.integration_auto_sync_service.apply_auto_note_ai_analyze(
            company_id=ctx.company_id,
            namespace_name=ns_name,
            provider_id=provider.strip(),
            auto_note_ai_analyze=body.auto_note_ai_analyze,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    refreshed = await container.namespace_repository.get(ns_name)
    crm = refreshed.crm_settings if refreshed is not None else None
    row = await connector.manifest_item(
        namespace_name=ns_name,
        company_id=ctx.company_id,
        user_id=ctx.user_id,
        crm_settings=crm,
    )
    return IntegrationManifestItem.model_validate(row)


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
