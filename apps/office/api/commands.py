"""Documents: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response

from apps.office.dependencies import ContainerDep
from apps.office.models.api import (
    OfficeCatalogCreateRequest,
    OfficeCatalogDetailResponse,
    OfficeCatalogItemsResponse,
    OfficeCatalogListResponse,
    OfficeCatalogMemberAddRequest,
    OfficeCatalogMembersResponse,
    OfficeCatalogPatchRequest,
    OfficeCatalogRagIndexDisableResponse,
    OfficeCatalogRagIndexEnableResponse,
    OfficeCatalogRagIndexRebuildResponse,
    OfficeCatalogRagIndexSettingsPatchRequest,
    OfficeCatalogRagIndexSettingsResponse,
    OfficeCatalogRagIndexStatusResponse,
    OfficeCatalogSemanticSearchRequest,
    OfficeCatalogSemanticSearchResponse,
    OfficeDocumentAiSummaryResponse,
    OfficeDocumentAppendTextRequest,
    OfficeDocumentCopyRequest,
    OfficeDocumentCreateResponse,
    OfficeDocumentEditorSessionResponse,
    OfficeDocumentEventItem,
    OfficeDocumentFromFileRequest,
    OfficeDocumentItem,
    OfficeDocumentListResponse,
    OfficeDocumentMetadataResponse,
    OfficeDocumentMoveRequest,
    OfficeDocumentMutationResponse,
    OfficeDocumentPreviewResponse,
    OfficeDocumentRenameRequest,
    OfficeDocumentRenameResponse,
    OfficeDocumentReplaceTextRequest,
    OfficeDocumentRevisionItem,
    OfficeDocumentShareCreateRequest,
    OfficeDocumentShareItem,
    OfficeDocumentsRagIndexStatusesRequest,
    OfficeDocumentsRagIndexStatusesResponse,
    OfficeEmptyCreateRequest,
    OfficeIntegrationStatusResponse,
    OfficeNamespaceCreateRequest,
    OfficeNamespaceCreateResponse,
    OfficeNamespaceTemplateItem,
    OfficeResourceAccessPatchRequest,
    OfficeResourceAccessResponse,
    OfficeResourceAccessRotateLinkResponse,
    OfficeSpreadsheetUpdateCellsRequest,
)
from apps.office.realtime.operations import (
    OfficeCatalogAccessRotatePayload,
    OfficeCatalogAccessUpdatePayload,
    OfficeCatalogIdPayload,
    OfficeCatalogMemberAddPayload,
    OfficeCatalogMemberRemovePayload,
    OfficeCatalogRagSearchPayload,
    OfficeCatalogRagSettingsPayload,
    OfficeCatalogUpdatePayload,
    OfficeDocumentAccessRotatePayload,
    OfficeDocumentAccessUpdatePayload,
    OfficeDocumentAppendTextPayload,
    OfficeDocumentCopyPayload,
    OfficeDocumentMovePayload,
    OfficeDocumentRenamePayload,
    OfficeDocumentReplaceTextPayload,
    OfficeDocumentSearchPayload,
    OfficeDocumentShareCreatePayload,
    OfficeDocumentsListPayload,
    OfficeDocumentUpdateCellsPayload,
    OfficeEmptyPayload,
    OfficeFileIdPayload,
    op_catalogs_access,
    op_catalogs_access_rotate_link,
    op_catalogs_access_update,
    op_catalogs_create,
    op_catalogs_ensure_path,
    op_catalogs_item,
    op_catalogs_items,
    op_catalogs_list,
    op_catalogs_member_add,
    op_catalogs_member_remove,
    op_catalogs_members_list,
    op_catalogs_rag_disable,
    op_catalogs_rag_enable,
    op_catalogs_rag_rebuild,
    op_catalogs_rag_search,
    op_catalogs_rag_settings,
    op_catalogs_rag_status,
    op_catalogs_remove,
    op_catalogs_update,
    op_company_members_list,
    op_documents_access,
    op_documents_access_rotate_link,
    op_documents_access_update,
    op_documents_ai_summary,
    op_documents_append_text,
    op_documents_bind,
    op_documents_copy,
    op_documents_create_from_file,
    op_documents_deleted_list,
    op_documents_editor_session,
    op_documents_empty,
    op_documents_events_list,
    op_documents_list,
    op_documents_metadata,
    op_documents_move,
    op_documents_permanent_remove,
    op_documents_preview,
    op_documents_rag_statuses,
    op_documents_remove,
    op_documents_rename,
    op_documents_replace_text,
    op_documents_restore,
    op_documents_revision_create,
    op_documents_revisions_list,
    op_documents_search,
    op_documents_share_create,
    op_documents_shares_list,
    op_documents_update_cells,
    op_integration_status,
    op_namespaces_create,
    op_namespaces_templates,
)
from core.api.team import TeamMemberResponse
from core.context import require_context
from core.documents.placement import (
    DocsBindResult,
    DocsEnsurePathRequest,
    DocsEnsurePathResult,
    DocsPlacement,
)
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.identity_models import Namespace
from core.namespace.operations import NamespacesListPayload, op_namespaces_list
from core.pagination import ListResponse, OffsetPage

router = APIRouter(tags=["office-commands"])

OfficeDocumentSortKey = Literal["created_at", "title", "file_size", "updated_at"]
OfficeDocumentSortOrder = Literal["asc", "desc"]


def _request_origin(http_request: Request) -> str:
    return build_service_base_url(http_request).rstrip("/")


@router.get("/integration/status", response_model=OfficeIntegrationStatusResponse)
async def integration_status(container: ContainerDep) -> OfficeIntegrationStatusResponse:
    return await op_integration_status(
        OfficeEmptyPayload(), user=require_context().user, container=container
    )


@router.get("/namespaces", response_model=OffsetPage[Namespace])
async def list_namespaces(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[Namespace]:
    return await op_namespaces_list(
        NamespacesListPayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.get("/namespaces/templates", response_model=OffsetPage[OfficeNamespaceTemplateItem])
async def list_namespace_templates(
    container: ContainerDep,
) -> OffsetPage[OfficeNamespaceTemplateItem]:
    return await op_namespaces_templates(
        OfficeEmptyPayload(), user=require_context().user, container=container
    )


@router.post("/namespaces", response_model=OfficeNamespaceCreateResponse, status_code=201)
async def create_namespace(
    container: ContainerDep, body: OfficeNamespaceCreateRequest
) -> OfficeNamespaceCreateResponse:
    return await op_namespaces_create(
        body, user=require_context().user, container=container
    )


@router.get("/company-members", response_model=ListResponse[TeamMemberResponse])
async def list_company_members(
    container: ContainerDep,
) -> ListResponse[TeamMemberResponse]:
    return await op_company_members_list(
        OfficeEmptyPayload(), user=require_context().user, container=container
    )


@router.get("/catalogs", response_model=OfficeCatalogListResponse)
async def list_catalogs(container: ContainerDep) -> OfficeCatalogListResponse:
    return await op_catalogs_list(
        OfficeEmptyPayload(), user=require_context().user, container=container
    )


@router.post("/catalogs/ensure-path", response_model=DocsEnsurePathResult)
async def ensure_catalog_path(
    container: ContainerDep, body: DocsEnsurePathRequest
) -> DocsEnsurePathResult:
    return await op_catalogs_ensure_path(
        body, user=require_context().user, container=container
    )


@router.post("/catalogs", response_model=OfficeCatalogDetailResponse)
async def create_catalog(
    container: ContainerDep, body: OfficeCatalogCreateRequest
) -> OfficeCatalogDetailResponse:
    return await op_catalogs_create(body, user=require_context().user, container=container)


@router.get("/catalogs/{catalog_id}", response_model=OfficeCatalogDetailResponse)
async def get_catalog(
    container: ContainerDep, catalog_id: str
) -> OfficeCatalogDetailResponse:
    return await op_catalogs_item(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.get("/catalogs/{catalog_id}/items", response_model=OfficeCatalogItemsResponse)
async def list_catalog_items(
    container: ContainerDep, catalog_id: str
) -> OfficeCatalogItemsResponse:
    return await op_catalogs_items(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.patch("/catalogs/{catalog_id}", response_model=OfficeCatalogDetailResponse)
async def update_catalog(
    container: ContainerDep, catalog_id: str, body: OfficeCatalogPatchRequest
) -> OfficeCatalogDetailResponse:
    return await op_catalogs_update(
        OfficeCatalogUpdatePayload(
            catalog_id=catalog_id,
            title=body.title,
            company_visible=body.company_visible,
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/catalogs/{catalog_id}", status_code=204)
async def delete_catalog(container: ContainerDep, catalog_id: str) -> Response:
    await op_catalogs_remove(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.post(
    "/catalogs/{catalog_id}/rag-index/enable",
    response_model=OfficeCatalogRagIndexEnableResponse,
)
async def enable_catalog_rag_index(
    container: ContainerDep, catalog_id: str
) -> OfficeCatalogRagIndexEnableResponse:
    return await op_catalogs_rag_enable(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/catalogs/{catalog_id}/rag-index/disable",
    response_model=OfficeCatalogRagIndexDisableResponse,
)
async def disable_catalog_rag_index(
    container: ContainerDep, catalog_id: str
) -> OfficeCatalogRagIndexDisableResponse:
    return await op_catalogs_rag_disable(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/catalogs/{catalog_id}/rag-index/rebuild",
    status_code=202,
    response_model=OfficeCatalogRagIndexRebuildResponse,
)
async def rebuild_catalog_rag_index(
    container: ContainerDep, catalog_id: str
) -> OfficeCatalogRagIndexRebuildResponse:
    return await op_catalogs_rag_rebuild(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/catalogs/{catalog_id}/rag-index/status",
    response_model=OfficeCatalogRagIndexStatusResponse,
)
async def catalog_rag_index_status(
    container: ContainerDep, catalog_id: str
) -> OfficeCatalogRagIndexStatusResponse:
    return await op_catalogs_rag_status(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.patch(
    "/catalogs/{catalog_id}/rag-index/settings",
    response_model=OfficeCatalogRagIndexSettingsResponse,
)
async def patch_catalog_rag_index_settings(
    container: ContainerDep,
    catalog_id: str,
    body: OfficeCatalogRagIndexSettingsPatchRequest,
) -> OfficeCatalogRagIndexSettingsResponse:
    return await op_catalogs_rag_settings(
        OfficeCatalogRagSettingsPayload(
            catalog_id=catalog_id,
            channels=body.channels,
            rrf_k=body.rrf_k,
            per_channel_top_k=body.per_channel_top_k,
            rerank=body.rerank,
            rerank_max_candidates=body.rerank_max_candidates,
            retrieval=body.retrieval,
            freshness_weight=body.freshness_weight,
            freshness_half_life_days=body.freshness_half_life_days,
            include_subcatalogs=body.include_subcatalogs,
            clear_search_options=body.clear_search_options,
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/catalogs/{catalog_id}/rag-index/search",
    response_model=OfficeCatalogSemanticSearchResponse,
)
async def search_catalog_rag_index(
    container: ContainerDep,
    catalog_id: str,
    body: OfficeCatalogSemanticSearchRequest,
) -> OfficeCatalogSemanticSearchResponse:
    return await op_catalogs_rag_search(
        OfficeCatalogRagSearchPayload(
            catalog_id=catalog_id,
            query=body.query,
            limit=body.limit,
            filters=body.filters,
            channels=body.channels,
            rrf_k=body.rrf_k,
            per_channel_top_k=body.per_channel_top_k,
            rerank=body.rerank,
            rerank_max_candidates=body.rerank_max_candidates,
            retrieval=body.retrieval,
            freshness_weight=body.freshness_weight,
            freshness_half_life_days=body.freshness_half_life_days,
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/catalogs/{catalog_id}/members", response_model=OfficeCatalogMembersResponse)
async def list_catalog_members(
    container: ContainerDep, catalog_id: str
) -> OfficeCatalogMembersResponse:
    return await op_catalogs_members_list(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.post("/catalogs/{catalog_id}/members", response_model=OfficeCatalogMembersResponse)
async def add_catalog_member(
    container: ContainerDep, catalog_id: str, body: OfficeCatalogMemberAddRequest
) -> OfficeCatalogMembersResponse:
    return await op_catalogs_member_add(
        OfficeCatalogMemberAddPayload(
            catalog_id=catalog_id,
            user_id=body.user_id,
            relation=body.relation,
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/catalogs/{catalog_id}/members/{member_user_id}", status_code=204)
async def remove_catalog_member(
    container: ContainerDep, catalog_id: str, member_user_id: str
) -> Response:
    await op_catalogs_member_remove(
        OfficeCatalogMemberRemovePayload(
            catalog_id=catalog_id, member_user_id=member_user_id
        ),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.get("/catalogs/{catalog_id}/access", response_model=OfficeResourceAccessResponse)
async def get_catalog_access(
    container: ContainerDep, catalog_id: str
) -> OfficeResourceAccessResponse:
    return await op_catalogs_access(
        OfficeCatalogIdPayload(catalog_id=catalog_id),
        user=require_context().user,
        container=container,
    )


@router.patch("/catalogs/{catalog_id}/access", response_model=OfficeResourceAccessResponse)
async def patch_catalog_access(
    container: ContainerDep,
    catalog_id: str,
    body: OfficeResourceAccessPatchRequest,
    http_request: Request,
) -> OfficeResourceAccessResponse:
    return await op_catalogs_access_update(
        OfficeCatalogAccessUpdatePayload(
            catalog_id=catalog_id,
            origin=_request_origin(http_request),
            company_visible=body.company_visible,
            link_enabled=body.link_enabled,
            link_permission=body.link_permission,
            members=body.members,
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/catalogs/{catalog_id}/access/link/rotate",
    response_model=OfficeResourceAccessRotateLinkResponse,
)
async def rotate_catalog_access_link(
    container: ContainerDep, catalog_id: str, http_request: Request
) -> OfficeResourceAccessRotateLinkResponse:
    return await op_catalogs_access_rotate_link(
        OfficeCatalogAccessRotatePayload(
            catalog_id=catalog_id, origin=_request_origin(http_request)
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/documents", response_model=OfficeDocumentListResponse)
async def list_documents(
    container: ContainerDep,
    catalog_id: Annotated[str | None, Query(min_length=1)] = None,
    catalog_ids: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=500)] = None,
    sort: Annotated[OfficeDocumentSortKey, Query()] = "updated_at",
    order: Annotated[OfficeDocumentSortOrder, Query()] = "desc",
) -> OfficeDocumentListResponse:
    raw: list[str] = []
    if catalog_ids:
        raw.extend(catalog_ids)
    if catalog_id is not None and catalog_id.strip() != "":
        raw.append(catalog_id.strip())
    return await op_documents_list(
        OfficeDocumentsListPayload(catalog_ids=raw, q=q, sort=sort, order=order),
        user=require_context().user,
        container=container,
    )


@router.post("/documents", response_model=OfficeDocumentCreateResponse)
async def create_document_from_uploaded_file(
    container: ContainerDep, body: OfficeDocumentFromFileRequest
) -> OfficeDocumentCreateResponse:
    return await op_documents_create_from_file(
        body, user=require_context().user, container=container
    )


@router.post("/documents/bind", response_model=DocsBindResult)
async def bind_file_to_catalog(
    container: ContainerDep, body: DocsPlacement
) -> DocsBindResult:
    return await op_documents_bind(body, user=require_context().user, container=container)


@router.post(
    "/documents/rag-index-statuses",
    response_model=OfficeDocumentsRagIndexStatusesResponse,
)
async def documents_rag_index_statuses(
    container: ContainerDep, body: OfficeDocumentsRagIndexStatusesRequest
) -> OfficeDocumentsRagIndexStatusesResponse:
    return await op_documents_rag_statuses(
        body, user=require_context().user, container=container
    )


@router.post("/documents/empty", response_model=OfficeDocumentCreateResponse)
async def create_empty_document(
    container: ContainerDep, body: OfficeEmptyCreateRequest
) -> OfficeDocumentCreateResponse:
    return await op_documents_empty(body, user=require_context().user, container=container)


@router.post(
    "/documents/{file_id}/editor-session",
    response_model=OfficeDocumentEditorSessionResponse,
)
async def document_editor_session(
    container: ContainerDep, file_id: str
) -> OfficeDocumentEditorSessionResponse:
    return await op_documents_editor_session(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/documents/{file_id}/mutations/replace-text",
    response_model=OfficeDocumentMutationResponse,
)
async def replace_document_text(
    container: ContainerDep, file_id: str, body: OfficeDocumentReplaceTextRequest
) -> OfficeDocumentMutationResponse:
    return await op_documents_replace_text(
        OfficeDocumentReplaceTextPayload(
            file_id=file_id,
            find=body.find,
            replace=body.replace,
            match_case=body.match_case,
            tool_call_id=body.tool_call_id,
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/documents/{file_id}/mutations/append-text",
    response_model=OfficeDocumentMutationResponse,
)
async def append_document_text(
    container: ContainerDep, file_id: str, body: OfficeDocumentAppendTextRequest
) -> OfficeDocumentMutationResponse:
    return await op_documents_append_text(
        OfficeDocumentAppendTextPayload(
            file_id=file_id,
            text=body.text,
            tool_call_id=body.tool_call_id,
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/documents/{file_id}/mutations/update-cells",
    response_model=OfficeDocumentMutationResponse,
)
async def update_document_cells(
    container: ContainerDep, file_id: str, body: OfficeSpreadsheetUpdateCellsRequest
) -> OfficeDocumentMutationResponse:
    return await op_documents_update_cells(
        OfficeDocumentUpdateCellsPayload(
            file_id=file_id,
            cells=body.cells,
            sheet=body.sheet,
            tool_call_id=body.tool_call_id,
        ),
        user=require_context().user,
        container=container,
    )


@router.patch("/documents/{file_id}", response_model=OfficeDocumentRenameResponse)
async def rename_document(
    container: ContainerDep, file_id: str, body: OfficeDocumentRenameRequest
) -> OfficeDocumentRenameResponse:
    return await op_documents_rename(
        OfficeDocumentRenamePayload(file_id=file_id, title=body.title),
        user=require_context().user,
        container=container,
    )


@router.delete("/documents/{file_id}", status_code=204)
async def delete_document(container: ContainerDep, file_id: str) -> Response:
    await op_documents_remove(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.get("/documents/deleted", response_model=OfficeDocumentListResponse)
async def list_deleted_documents(container: ContainerDep) -> OfficeDocumentListResponse:
    return await op_documents_deleted_list(
        OfficeEmptyPayload(), user=require_context().user, container=container
    )


@router.post("/documents/{file_id}/restore", response_model=OfficeDocumentItem)
async def restore_document(container: ContainerDep, file_id: str) -> OfficeDocumentItem:
    return await op_documents_restore(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.delete("/documents/{file_id}/permanent", status_code=204)
async def permanent_delete_document(container: ContainerDep, file_id: str) -> Response:
    await op_documents_permanent_remove(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )
    return Response(status_code=204)


@router.post("/documents/{file_id}/move", response_model=OfficeDocumentItem)
async def move_document(
    container: ContainerDep, file_id: str, body: OfficeDocumentMoveRequest
) -> OfficeDocumentItem:
    return await op_documents_move(
        OfficeDocumentMovePayload(file_id=file_id, catalog_id=body.catalog_id),
        user=require_context().user,
        container=container,
    )


@router.post("/documents/{file_id}/copy", response_model=OfficeDocumentCreateResponse)
async def copy_document(
    container: ContainerDep, file_id: str, body: OfficeDocumentCopyRequest
) -> OfficeDocumentCreateResponse:
    return await op_documents_copy(
        OfficeDocumentCopyPayload(
            file_id=file_id, catalog_id=body.catalog_id, title=body.title
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/documents/search", response_model=OfficeDocumentListResponse)
async def search_documents(
    container: ContainerDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
) -> OfficeDocumentListResponse:
    return await op_documents_search(
        OfficeDocumentSearchPayload(q=q),
        user=require_context().user,
        container=container,
    )


@router.get("/documents/{file_id}/access", response_model=OfficeResourceAccessResponse)
async def get_document_access(
    container: ContainerDep, file_id: str
) -> OfficeResourceAccessResponse:
    return await op_documents_access(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.patch("/documents/{file_id}/access", response_model=OfficeResourceAccessResponse)
async def patch_document_access(
    container: ContainerDep,
    file_id: str,
    body: OfficeResourceAccessPatchRequest,
    http_request: Request,
) -> OfficeResourceAccessResponse:
    return await op_documents_access_update(
        OfficeDocumentAccessUpdatePayload(
            file_id=file_id,
            origin=_request_origin(http_request),
            company_visible=body.company_visible,
            link_enabled=body.link_enabled,
            link_permission=body.link_permission,
            members=body.members,
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/documents/{file_id}/access/link/rotate",
    response_model=OfficeResourceAccessRotateLinkResponse,
)
async def rotate_document_access_link(
    container: ContainerDep, file_id: str, http_request: Request
) -> OfficeResourceAccessRotateLinkResponse:
    return await op_documents_access_rotate_link(
        OfficeDocumentAccessRotatePayload(
            file_id=file_id, origin=_request_origin(http_request)
        ),
        user=require_context().user,
        container=container,
    )


@router.get("/documents/{file_id}/preview", response_model=OfficeDocumentPreviewResponse)
async def document_preview(
    container: ContainerDep, file_id: str
) -> OfficeDocumentPreviewResponse:
    return await op_documents_preview(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.post("/documents/{file_id}/shares", response_model=OfficeDocumentShareItem)
async def create_document_share(
    container: ContainerDep,
    file_id: str,
    body: OfficeDocumentShareCreateRequest,
    http_request: Request,
) -> OfficeDocumentShareItem:
    return await op_documents_share_create(
        OfficeDocumentShareCreatePayload(
            file_id=file_id,
            origin=_request_origin(http_request),
            permission=body.permission,
            expires_in_hours=body.expires_in_hours,
        ),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/documents/{file_id}/shares",
    response_model=ListResponse[OfficeDocumentShareItem],
)
async def list_document_shares(
    container: ContainerDep, file_id: str
) -> ListResponse[OfficeDocumentShareItem]:
    return await op_documents_shares_list(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/documents/{file_id}/revisions",
    response_model=ListResponse[OfficeDocumentRevisionItem],
)
async def list_document_revisions(
    container: ContainerDep, file_id: str
) -> ListResponse[OfficeDocumentRevisionItem]:
    return await op_documents_revisions_list(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.post("/documents/{file_id}/revisions", response_model=OfficeDocumentRevisionItem)
async def create_document_revision(
    container: ContainerDep, file_id: str
) -> OfficeDocumentRevisionItem:
    return await op_documents_revision_create(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/documents/{file_id}/events",
    response_model=ListResponse[OfficeDocumentEventItem],
)
async def list_document_events(
    container: ContainerDep, file_id: str
) -> ListResponse[OfficeDocumentEventItem]:
    return await op_documents_events_list(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.get("/documents/{file_id}/metadata", response_model=OfficeDocumentMetadataResponse)
async def document_metadata(
    container: ContainerDep, file_id: str
) -> OfficeDocumentMetadataResponse:
    return await op_documents_metadata(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/documents/{file_id}/ai-summary",
    response_model=OfficeDocumentAiSummaryResponse,
)
async def document_ai_summary(
    container: ContainerDep, file_id: str
) -> OfficeDocumentAiSummaryResponse:
    return await op_documents_ai_summary(
        OfficeFileIdPayload(file_id=file_id),
        user=require_context().user,
        container=container,
    )
