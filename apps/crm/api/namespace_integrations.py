"""REST-зеркало интеграций namespace: те же `op_*`, что и Centrifugo RPC `platform.event`."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from apps.crm.di import Di
from apps.crm.models.api import (
    AutoNoteAiAnalyzeUpdateRequest,
    IntegrationAuthorizeResponse,
    IntegrationAutoSyncUpdateRequest,
    IntegrationManifestItem,
    IntegrationSyncStats,
)
from apps.crm.models.task import CRMTask
from apps.crm.realtime.operations import (
    CrmIntegrationAuthorizePayload,
    CrmIntegrationAutoNoteAiPayload,
    CrmIntegrationAutoSyncPayload,
    CrmIntegrationNamespacePayload,
    CrmIntegrationProviderPayload,
    op_namespace_integrations_authorize,
    op_namespace_integrations_auto_note_ai,
    op_namespace_integrations_auto_sync,
    op_namespace_integrations_custom_fields_sync,
    op_namespace_integrations_list,
    op_namespace_integrations_sync,
)
from core.context import require_context
from core.pagination import ListResponse

router = APIRouter(prefix="/namespaces", tags=["namespace-integrations"])


@router.get(
    "/{namespace_name}/integrations",
    response_model=ListResponse[IntegrationManifestItem],
)
async def list_namespace_integrations(
    namespace_name: str,
    di: Di,
) -> ListResponse[IntegrationManifestItem]:
    return await op_namespace_integrations_list(
        CrmIntegrationNamespacePayload(namespace_name=namespace_name),
        user=require_context().user,
        di=di,
    )


@router.get(
    "/{namespace_name}/integrations/{provider}/authorize",
    response_model=IntegrationAuthorizeResponse,
)
async def integration_authorize_url(
    request: Request,
    namespace_name: str,
    provider: str,
    di: Di,
    subdomain: Annotated[str, Query(min_length=1)],
    return_path: Annotated[str, Query(min_length=1)],
    return_origin: Annotated[str | None, Query()] = None,
) -> IntegrationAuthorizeResponse:
    return await op_namespace_integrations_authorize(
        CrmIntegrationAuthorizePayload(
            namespace_name=namespace_name,
            provider_id=provider,
            subdomain=subdomain,
            return_path=return_path,
            return_origin=return_origin,
            accept_language=request.headers.get("accept-language"),
            language_cookie=request.cookies.get("language"),
            brand_host=request.headers.get("host"),
        ),
        user=require_context().user,
        di=di,
    )


@router.patch(
    "/{namespace_name}/integrations/{provider}/auto-sync",
    response_model=IntegrationManifestItem,
)
async def integration_auto_sync_patch(
    namespace_name: str,
    provider: str,
    body: IntegrationAutoSyncUpdateRequest,
    di: Di,
) -> IntegrationManifestItem:
    return await op_namespace_integrations_auto_sync(
        CrmIntegrationAutoSyncPayload(
            namespace_name=namespace_name,
            provider_id=provider,
            auto_sync_enabled=body.auto_sync_enabled,
            auto_sync_cron=body.auto_sync_cron,
            auto_sync_timezone=body.auto_sync_timezone,
        ),
        user=require_context().user,
        di=di,
    )


@router.patch(
    "/{namespace_name}/integrations/{provider}/auto-note-ai-analyze",
    response_model=IntegrationManifestItem,
)
async def integration_auto_note_ai_analyze_patch(
    namespace_name: str,
    provider: str,
    body: AutoNoteAiAnalyzeUpdateRequest,
    di: Di,
) -> IntegrationManifestItem:
    return await op_namespace_integrations_auto_note_ai(
        CrmIntegrationAutoNoteAiPayload(
            namespace_name=namespace_name,
            provider_id=provider,
            auto_note_ai_analyze=body.auto_note_ai_analyze,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{namespace_name}/integrations/{provider}/sync")
async def integration_sync(
    namespace_name: str,
    provider: str,
    di: Di,
    response: Response,
) -> CRMTask | IntegrationSyncStats:
    result = await op_namespace_integrations_sync(
        CrmIntegrationProviderPayload(namespace_name=namespace_name, provider_id=provider),
        user=require_context().user,
        di=di,
    )
    if isinstance(result, CRMTask):
        response.status_code = 202
    return result


@router.post("/{namespace_name}/integrations/{provider}/custom_fields/sync")
async def integration_custom_fields_sync(
    namespace_name: str,
    provider: str,
    di: Di,
    response: Response,
) -> CRMTask | IntegrationSyncStats:
    result = await op_namespace_integrations_custom_fields_sync(
        CrmIntegrationProviderPayload(namespace_name=namespace_name, provider_id=provider),
        user=require_context().user,
        di=di,
    )
    if isinstance(result, CRMTask):
        response.status_code = 202
    return result
