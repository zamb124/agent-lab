"""Бизнес-функции Documents: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Never
from urllib.parse import quote

from httpx import HTTPError, HTTPStatusError
from pydantic import Field

from apps.office.config import get_office_settings
from apps.office.di import Di
from apps.office.models.api import (
    OfficeCatalogCreateRequest,
    OfficeCatalogDetailResponse,
    OfficeCatalogItemsResponse,
    OfficeCatalogListItem,
    OfficeCatalogListResponse,
    OfficeCatalogMemberAddRequest,
    OfficeCatalogMemberItem,
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
from apps.office.models.event import OfficeDocumentEvent
from apps.office.models.link import DocumentLink
from apps.office.models.revision import OfficeDocumentRevision
from apps.office.services.document_lifecycle import document_title, records_to_items
from apps.office.services.document_mutations import (
    DocumentMutationError,
    append_text_to_document,
    replace_text_in_document,
    update_spreadsheet_cells,
)
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from apps.office.services.minimal_ooxml import minimal_pptx_bytes, minimal_xlsx_bytes
from apps.office.services.viewer_service import integration_configured
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation
from core.clients.onlyoffice import sign_onlyoffice_jwt_hs256
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.documents.catalog import DocumentCatalog
from core.documents.placement import DocumentEnsureRequest, DocumentEnsureResult, DocumentPlacement
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SystemPrincipal
from core.files.registry import default_retention_for_source
from core.files.types import FileCategory
from core.http import get_httpx_client
from core.logging import get_log_context, get_logger
from core.models.base import StrictBaseModel
from core.models.identity_models import Company, User
from core.pagination import ListResponse, OffsetPage
from core.request_scope import CompanyScope, NamespaceScope, require_company, require_namespace
from core.types import JsonObject, JsonValue, parse_json_object, require_json_array
from core.websocket import (
    EmptyPayload,
    WsCommandError,
    raise_conflict,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)

logger = get_logger(__name__)

_EMPTY_DOCX = Path(__file__).resolve().parent.parent / "templates" / "empty.docx"
_CRM_API_V1_PREFIX = "/crm/api/v1"
_LOCK_POLL_SECONDS = 2.0
OfficeDocumentSortKey = Literal["created_at", "title", "file_size", "updated_at"]
OfficeDocumentSortOrder = Literal["asc", "desc"]
_DocumentBytesMutation = Callable[[bytes, str], bytes | tuple[bytes, int]]

ONLYOFFICE_COMMAND_ERROR_DETAILS = {
    1: "document key is missing or no open document with this key was found",
    2: "callback URL is not correct or is not reachable from Document Server",
    3: "internal Document Server error",
    4: "no changes were applied before forcesave",
    5: "command is not correct",
    6: "invalid Document Server JWT token",
}


class OfficeCatalogIdPayload(StrictBaseModel):
    catalog_id: str = Field(min_length=1)


class OfficeCatalogUpdatePayload(OfficeCatalogPatchRequest):
    catalog_id: str = Field(min_length=1)


class OfficeCatalogRagSettingsPayload(OfficeCatalogRagIndexSettingsPatchRequest):
    catalog_id: str = Field(min_length=1)


class OfficeCatalogRagSearchPayload(OfficeCatalogSemanticSearchRequest):
    catalog_id: str = Field(min_length=1)


class OfficeCatalogMemberAddPayload(OfficeCatalogMemberAddRequest):
    catalog_id: str = Field(min_length=1)


class OfficeCatalogMemberRemovePayload(StrictBaseModel):
    catalog_id: str = Field(min_length=1)
    member_user_id: str = Field(min_length=1)


class OfficeCatalogAccessUpdatePayload(OfficeResourceAccessPatchRequest):
    catalog_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)


class OfficeCatalogAccessRotatePayload(StrictBaseModel):
    catalog_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)


class OfficeFileIdPayload(StrictBaseModel):
    file_id: str = Field(min_length=1)


class OfficeDocumentsListPayload(StrictBaseModel):
    catalog_ids: list[str] = Field(min_length=1)
    q: str | None = Field(default=None, max_length=500)
    sort: OfficeDocumentSortKey = "updated_at"
    order: OfficeDocumentSortOrder = "desc"


class OfficeDocumentSearchPayload(StrictBaseModel):
    q: str = Field(min_length=1, max_length=500)


class OfficeDocumentRenamePayload(OfficeDocumentRenameRequest):
    file_id: str = Field(min_length=1)


class OfficeDocumentMovePayload(OfficeDocumentMoveRequest):
    file_id: str = Field(min_length=1)


class OfficeDocumentCopyPayload(OfficeDocumentCopyRequest):
    file_id: str = Field(min_length=1)


class OfficeDocumentReplaceTextPayload(OfficeDocumentReplaceTextRequest):
    file_id: str = Field(min_length=1)


class OfficeDocumentAppendTextPayload(OfficeDocumentAppendTextRequest):
    file_id: str = Field(min_length=1)


class OfficeDocumentUpdateCellsPayload(OfficeSpreadsheetUpdateCellsRequest):
    file_id: str = Field(min_length=1)


class OfficeDocumentAccessUpdatePayload(OfficeResourceAccessPatchRequest):
    file_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)


class OfficeDocumentAccessRotatePayload(StrictBaseModel):
    file_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)


class OfficeDocumentShareCreatePayload(OfficeDocumentShareCreateRequest):
    file_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)






async def namespace_scope(di: Di) -> NamespaceScope:
    return await require_namespace(di.namespace_service)


def _company_scope() -> CompanyScope:
    return require_company()


def raise_from_service_client(service: str, exc: ServiceClientError) -> Never:
    message = str(exc)
    match = re.match(r"HTTP (\d{3})", message)
    if match:
        code = int(match.group(1))
        if code == 404:
            raise WsCommandError("not_found", message, error_code='not_found') from exc
        if code == 403:
            raise WsCommandError("forbidden", message, error_code='forbidden') from exc
        if 400 <= code < 500:
            raise WsCommandError("ws_invalid_payload", message, error_code='ws_invalid_payload') from exc
    raise WsCommandError(
        "internal",
        f"Service {service} is unavailable or returned an error: {message}",
              error_code='internal',
          ) from exc


def raise_from_catalog_rag_value_error(exc: ValueError) -> Never:
    message = str(exc)
    if message == "Catalog not found":
        raise WsCommandError("not_found", message, error_code='not_found') from exc
    if message in {
        "RAG index is not enabled for the catalog",
        "No indexed catalogs to search",
    }:
        raise WsCommandError("conflict", message, error_code='conflict') from exc
    raise WsCommandError("ws_invalid_payload", message, error_code='ws_invalid_payload') from exc


async def index_binding_if_catalog_enabled(
    di: Di,
    binding: FileRecord,
    *,
    scope_company_id: str | None = None,
    scope_workspace_namespace: str | None = None,
    scope_user_id: str | None = None,
) -> None:
    _ = await di.catalog_rag_index_service.index_binding(
        binding,
        scope_company_id=scope_company_id,
        scope_workspace_namespace=scope_workspace_namespace,
        scope_user_id=scope_user_id,
    )


async def index_binding_if_catalog_enabled_with_job_context(
    di: Di,
    binding: FileRecord,
    *,
    company_id: str,
    workspace_namespace: str,
    user_id: str,
) -> None:
    normalized_company_id = company_id.strip()
    normalized_namespace = workspace_namespace.strip()
    normalized_user_id = user_id.strip()
    if normalized_company_id == "":
        raise ValueError("company_id is required")
    if normalized_namespace == "":
        raise ValueError("workspace_namespace is required")
    if normalized_user_id == "":
        raise ValueError("user_id is required")

    company = await Company.get(normalized_company_id)
    if company is None:
        raise ValueError(f"Company not found: {normalized_company_id}")
    user = await User.get(normalized_user_id)
    if user is None:
        raise ValueError(f"User not found: {normalized_user_id}")

    log_ctx = get_log_context()
    trace_raw = log_ctx.get("trace_id")
    trace_id = (
        trace_raw.strip()
        if isinstance(trace_raw, str) and trace_raw.strip() != ""
        else f"office-callback:{binding.file_id}"
    )
    session_id = f"office-callback:{binding.file_id}"
    previous_context = get_context()
    job_context = build_job_context(
        company=company,
        user=user,
        host="office_onlyoffice_callback",
        trace_id=trace_id,
        session_id=session_id,
        channel="office",
    ).model_copy(update={"active_namespace": normalized_namespace})
    _ = set_context(job_context)
    try:
        await index_binding_if_catalog_enabled(
            di,
            binding,
            scope_company_id=normalized_company_id,
            scope_workspace_namespace=normalized_namespace,
            scope_user_id=normalized_user_id,
        )
    finally:
        if previous_context is not None:
            _ = set_context(previous_context)
        else:
            clear_context()


async def unindex_binding_from_catalog(
    di: Di,
    catalog_id: str,
    file_id: str,
) -> None:
    await di.catalog_rag_index_service.unindex_binding(catalog_id, file_id)


async def _sync_document_created_or_rollback(
    di: Di,
    row: FileRecord,
    *,
    owner_user_id: str,
) -> None:
    try:
        await di.office_access_service.sync_document_created(
            row,
            owner_user_id=owner_user_id,
        )
    except Exception:
        _ = await di.files_service.delete(row.file_id)
        raise


async def _require_catalog_view(
    di: Di,
    catalog_id: str,
    user_id: str,
    *,
    missing_as: Literal["not_found", "forbidden"] = "not_found",
) -> None:
    allowed = await di.authz_service.can_view(
        AuthzObject.document_catalog(catalog_id),
        user_id=user_id,
    )
    if allowed:
        return
    if missing_as == "forbidden":
        raise WsCommandError("forbidden", "No access to catalog", error_code='forbidden')
    raise WsCommandError("not_found", "Catalog not found", error_code='not_found')


async def _require_catalog_admin(
    di: Di,
    catalog_id: str,
    user_id: str,
) -> None:
    try:
        await di.authz_service.require_can_admin(
            AuthzObject.document_catalog(catalog_id),
            user_id=user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)


async def _require_catalog_share(
    di: Di,
    catalog_id: str,
    user_id: str,
) -> None:
    try:
        await di.authz_service.require_relation(
            AuthzRelation.CAN_SHARE,
            AuthzObject.document_catalog(catalog_id),
            user_id=user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)


async def require_binding_catalog_access(
    di: Di,
    row: FileRecord,
    user_id: str,
) -> None:
    allowed = await di.office_access_service.user_can_view_document(
        row,
        company_id=row.company_id or "",
        user_id=user_id,
    )
    if not allowed:
        raise WsCommandError("forbidden", "No access to the document catalog", error_code='forbidden')


async def _require_trashed_binding_access(
    di: Di,
    row: FileRecord,
    user_id: str,
) -> None:
    allowed = await di.office_access_service.user_can_manage_trashed_binding(
        row,
        company_id=row.company_id or "",
        user_id=user_id,
    )
    if not allowed:
        raise WsCommandError("forbidden", "No access to the document catalog", error_code='forbidden')


async def _resolve_catalog_for_create(
    di: Di,
    *,
    user_id: str,
    catalog_id: str | None,
) -> str:
    if catalog_id is None or catalog_id.strip() == "":
        raise WsCommandError("ws_invalid_payload", "Specify catalog_id: create a catalog first", error_code='ws_invalid_payload')
    cid = catalog_id.strip()
    allowed = await di.authz_service.can_view(
        AuthzObject.document_catalog(cid),
        user_id=user_id,
    )
    if not allowed:
        raise WsCommandError("forbidden", "No access to catalog", error_code='forbidden')
    return cid


async def _user_display(user_id: str) -> tuple[str, str | None]:
    user = await User.get(user_id)
    if user is not None:
        return user.name or user_id, user.avatar_url
    return user_id, None


async def _build_catalog_detail_response(
    di: Di,
    *,
    catalog: DocumentCatalog,
    current_user_id: str,
) -> OfficeCatalogDetailResponse:
    access = di.office_access_service
    owner_user_id = await access.resolve_catalog_owner_user_id(catalog.catalog_id)
    company_visible = await access.catalog_is_company_visible(
        catalog.catalog_id,
        catalog.company_id,
    )
    display_name, avatar_url = await _user_display(owner_user_id)
    return OfficeCatalogDetailResponse(
        catalog_id=catalog.catalog_id,
        parent_catalog_id=catalog.parent_catalog_id,
        title=catalog.title,
        owner_user_id=owner_user_id,
        owner_display_name=display_name,
        owner_avatar_url=avatar_url,
        is_owner=owner_user_id == current_user_id,
        company_visible=company_visible,
    )


async def _build_catalog_list_item(
    di: Di,
    *,
    catalog: DocumentCatalog,
    file_count: int,
    current_user_id: str,
) -> OfficeCatalogListItem:
    access = di.office_access_service
    owner_user_id = catalog.owner_user_id
    company_visible = await access.catalog_is_company_visible(
        catalog.catalog_id,
        catalog.company_id,
    )
    display_name, avatar_url = await _user_display(owner_user_id)
    rag_service = di.catalog_rag_index_service
    return OfficeCatalogListItem(
        catalog_id=catalog.catalog_id,
        parent_catalog_id=catalog.parent_catalog_id,
        title=catalog.title,
        file_count=file_count,
        owner_user_id=owner_user_id,
        owner_display_name=display_name,
        owner_avatar_url=avatar_url,
        is_owner=owner_user_id == current_user_id,
        company_visible=company_visible,
        rag_index_enabled=catalog.rag_index_enabled,
        rag_index_include_subcatalogs=catalog.rag_index_include_subcatalogs,
        rag_index_search_options=rag_service.catalog_search_options_model(catalog),
    )


async def _list_catalog_member_items(
    di: Di,
    *,
    catalog_id: str,
    company_id: str,
    namespace: str,
) -> list[OfficeCatalogMemberItem]:
    access_response = await di.office_access_service.get_catalog_access(
        catalog_id,
        company_id,
        namespace,
    )
    items: list[OfficeCatalogMemberItem] = []
    for member in access_response.members:
        display_name, avatar_url = await _user_display(member.user_id)
        items.append(
            OfficeCatalogMemberItem(
                user_id=member.user_id,
                display_name=display_name,
                avatar_url=avatar_url,
                relation=member.relation,
            )
        )
    return items


def _catalog_member_relation_to_authz(relation: str) -> AuthzRelation:
    if relation == "editor":
        return AuthzRelation.EDITOR
    if relation == "viewer":
        return AuthzRelation.VIEWER
    raise ValueError(f"unsupported member relation: {relation}")


def _safe_filename_stem(title: str) -> str:
    cleaned = re.sub(r"[^\w\-. ]+", "_", title.strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._ ")[:200]
    if not cleaned:
        return "document"
    return cleaned


def _document_name_with_source_extension(title: str | None, source_name: str) -> str | None:
    """Bind/rename title → имя файла в дереве: сохраняет расширение исходника."""
    if title is None:
        return None
    name = title.strip()
    if name == "":
        return None
    source_suffix = Path(source_name).suffix
    if source_suffix != "" and Path(name).suffix == "":
        return f"{name}{source_suffix}"
    return name


def editor_embed_url(file_id: str, namespace: str) -> str:
    return f"/documents/embed/edit/{quote(file_id, safe='')}?namespace={quote(namespace, safe='')}"


def onlyoffice_document_key(file_id: str, checksum: str | None) -> str:
    safe_checksum = re.sub(r"[^a-zA-Z0-9_-]", "", checksum or "")[:24]
    if not safe_checksum:
        return file_id
    return f"{file_id}_{safe_checksum}"


def _document_mutation_lock_key(file_id: str) -> str:
    return f"office:document:{file_id}:mutation"


def _document_mutation_lock_release_channel(file_id: str) -> str:
    return f"office:document:{file_id}:mutation:released"


@asynccontextmanager
async def document_mutation_lock(
    di: Di,
    file_id: str,
    *,
    wait_timeout_seconds: float = 45.0,
):
    client = di.redis_client
    lock_key = _document_mutation_lock_key(file_id)
    release_channel = _document_mutation_lock_release_channel(file_id)
    token = uuid.uuid4().hex
    deadline = asyncio.get_running_loop().time() + wait_timeout_seconds

    ok = await client.set_nx(lock_key, token, 120)
    if not ok:
        pubsub = await client.open_pubsub()
        await pubsub.subscribe(release_channel)
        try:
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise WsCommandError("conflict", "Document is already being modified", error_code='conflict')
                _ = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=min(remaining, _LOCK_POLL_SECONDS),
                )
                ok = await client.set_nx(lock_key, token, 120)
                if ok:
                    break
        finally:
            await pubsub.unsubscribe(release_channel)
            await pubsub.aclose()

    try:
        yield
    finally:
        _ = await client.delete(lock_key)
        _ = await client.publish(release_channel, "released")


def _document_server_command_base_url() -> str:
    settings = get_office_settings()
    dev_upstream = (settings.server.document_server_dev_upstream_url or "").strip().rstrip("/")
    if settings.server.env in ("development", "test") and dev_upstream:
        return dev_upstream
    return settings.office.document_server_public_url.strip().rstrip("/")


async def post_onlyoffice_command(
    *,
    payload: JsonObject,
    file_id: str,
    command_name: str,
    timeout: float = 10.0,
) -> int | None:
    settings = get_office_settings()
    integ = settings.office
    document_server = _document_server_command_base_url()
    if not document_server:
        return None
    body: JsonObject = {"token": sign_onlyoffice_jwt_hs256(payload, integ.jwt_secret)}
    key = str(payload.get("key") or "").strip()
    url = f"{document_server}/command"
    if key:
        url = f"{url}?shardkey={quote(key, safe='')}"
    try:
        async with get_httpx_client(timeout=timeout) as client:
            response = await client.post(url, json=body)
            _ = response.raise_for_status()
    except HTTPStatusError as exc:
        logger.exception(
            "office.onlyoffice.command.failed.mutation.file_id",
            file_id=file_id,
            command=command_name,
            http_status=exc.response.status_code,
            response=exc.response.text[:500],
        )
        raise WsCommandError("conflict", f"OnlyOffice {command_name} command failed", error_code='conflict') from exc
    except HTTPError as exc:
        logger.exception(
            "office.onlyoffice.command.failed.mutation.file_id",
            file_id=file_id,
            command=command_name,
            http_status=None,
            response='',
        )
        raise WsCommandError("conflict", f"OnlyOffice {command_name} command failed", error_code='conflict') from exc
    data = parse_json_object(response.content, "OnlyOffice command response")
    if "error" not in data:
        raise WsCommandError("conflict", f"OnlyOffice {command_name} returned invalid response", error_code='conflict')
    error_code = data["error"]
    if not isinstance(error_code, str | int):
        raise WsCommandError("conflict", f"OnlyOffice {command_name} returned invalid response", error_code='conflict')
    try:
        code = int(error_code)
    except ValueError:
        raise WsCommandError(
            "conflict", f"OnlyOffice {command_name} returned invalid response",
                  error_code='conflict',
              ) from None
    if code != 0:
        logger.warning(
            "office.onlyoffice.command.returned.error.file_id",
            file_id=file_id,
            command=command_name,
            code=code,
            detail=ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, 'unknown error'),
        )
    else:
        logger.info(
            "office.onlyoffice.command.accepted.file_id.command",
            file_id=file_id,
            command=command_name,
            key=key,
        )
    return code


async def force_save_open_editor_if_needed(*, file_id: str, document_key: str) -> int | None:
    code = await post_onlyoffice_command(
        payload={
            "c": "forcesave",
            "key": document_key,
            "userdata": f"sync:{file_id}:{uuid.uuid4().hex}",
        },
        file_id=file_id,
        command_name="forcesave",
    )
    if code is None or code in (0, 1, 4):
        return code
    detail = ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error")
    raise WsCommandError("conflict", f"OnlyOffice forcesave failed: error={code} ({detail})", error_code='conflict')


async def drop_open_editor_sessions(*, file_id: str, document_key: str) -> None:
    code = await post_onlyoffice_command(
        payload={"c": "drop", "key": document_key},
        file_id=file_id,
        command_name="drop",
    )
    if code is None or code in (0, 1):
        return
    detail = ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error")
    raise WsCommandError("conflict", f"OnlyOffice drop failed: error={code} ({detail})", error_code='conflict')


async def wait_for_file_change_after_forcesave(
    *,
    di: Di,
    file_id: str,
    previous_checksum: str | None,
    previous_file_size: int | None,
    max_iterations: int = 90,
    raise_on_timeout: bool = True,
) -> bool:
    for _ in range(max_iterations):
        await asyncio.sleep(0.5)
        meta = await di.files_service.get_optional(file_id)
        if meta is None:
            raise WsCommandError("not_found", "File not found", error_code='not_found')
        if meta.checksum != previous_checksum or meta.file_size != previous_file_size:
            logger.info(
                "office.onlyoffice.forcesave.materialized.file_id.old_size",
                file_id=file_id,
                old_size=previous_file_size,
                new_size=meta.file_size,
            )
            return True
    logger.warning(
        "office.onlyoffice.forcesave.callback.update.file",
        file_id=file_id,
        old_size=previous_file_size,
        old_checksum=previous_checksum,
    )
    if raise_on_timeout:
        raise WsCommandError("conflict", "Timed out waiting for the open editor to save", error_code='conflict')
    return False


def _sort_office_document_items(
    items: list[OfficeDocumentItem],
    sort: OfficeDocumentSortKey,
    order: OfficeDocumentSortOrder,
) -> list[OfficeDocumentItem]:
    reverse = order == "desc"

    def sort_key(item: OfficeDocumentItem) -> str | int | float:
        if sort == "title":
            return item.title.casefold()
        if sort == "file_size":
            return item.file_size
        if sort == "updated_at":
            return item.updated_at.timestamp()
        return item.created_at.timestamp()

    return sorted(items, key=sort_key, reverse=reverse)


def _record_meta(record: FileRecord) -> tuple[str, str | None]:
    return resolve_binding_metadata(
        record.original_name,
        record.content_type.split(";", 1)[0].strip(),
    )


def _binding_catalog_id(record: FileRecord) -> str:
    catalog_id = record.catalog_id
    if catalog_id is None:
        raise WsCommandError("not_found", "Binding not found", error_code="not_found")
    return catalog_id


async def load_binding(
    scope: NamespaceScope,
    file_id: str,
    *,
    allow_deleted: bool = False,
    require_trashed: bool = False,
) -> FileRecord:
    row = await FileRecord.for_company(file_id, scope.company_id)
    if row is None or row.catalog_id is None:
        raise WsCommandError("not_found", "Binding not found", error_code="not_found")
    catalog = await DocumentCatalog.catalog_in_namespace(
        row.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Binding not found", error_code="not_found")
    if require_trashed:
        if row.deleted_at is None:
            raise WsCommandError("not_found", "Binding not found in trash", error_code="not_found")
        return row
    if row.deleted_at is not None and not allow_deleted:
        raise WsCommandError("not_found", "Binding not found", error_code="not_found")
    return row


async def op_integration_status(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> OfficeIntegrationStatusResponse:
    _ = payload, user, di
    configured, detail = integration_configured()
    return OfficeIntegrationStatusResponse(configured=configured, detail=detail)


async def op_namespaces_templates(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[OfficeNamespaceTemplateItem]:
    _ = payload, user
    _ = _company_scope()
    path = f"{_CRM_API_V1_PREFIX}/namespaces/templates"
    try:
        raw = await di.service_client.get("crm", path)
    except ServiceClientError as exc:
        raise_from_service_client("crm", exc)
    raw_items_value = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(raw_items_value, list):
        raise WsCommandError("internal", "CRM: invalid namespace template list format", error_code='internal')
    raw_items = require_json_array(raw_items_value, "crm.namespace_templates.items")
    out: list[OfficeNamespaceTemplateItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise WsCommandError("internal", "CRM: namespace template item is not an object", error_code='internal')
        template_id = item.get("template_id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise WsCommandError("internal", "CRM: template has no template_id", error_code='internal')
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WsCommandError("internal", "CRM: template has no name", error_code='internal')
        description = item.get("description")
        icon = item.get("icon")
        entity_types = item.get("entity_type_ids")
        entity_type_ids: list[str] = []
        if isinstance(entity_types, list):
            entity_type_ids = [str(value) for value in entity_types if isinstance(value, str) and value.strip()]
        out.append(
            OfficeNamespaceTemplateItem(
                template_id=template_id.strip(),
                name=name.strip(),
                description=description.strip() if isinstance(description, str) and description.strip() else None,
                icon=icon.strip() if isinstance(icon, str) and icon.strip() else None,
                is_system=bool(item.get("is_system")),
                entity_type_ids=entity_type_ids,
            )
        )
    return OffsetPage[OfficeNamespaceTemplateItem](
        items=out, total=len(out), limit=len(out), offset=0
    )


async def op_namespaces_create(
    payload: OfficeNamespaceCreateRequest,
    *,
    user: User,
    di: Di,
) -> OfficeNamespaceCreateResponse:
    _ = user
    _ = _company_scope()
    path = f"{_CRM_API_V1_PREFIX}/namespaces"
    body = {
        "name": payload.name.strip(),
        "description": payload.description.strip() if payload.description else None,
        "template_id": payload.template_id.strip(),
    }
    try:
        raw = await di.service_client.post("crm", path, json=body)
    except ServiceClientError as exc:
        raise_from_service_client("crm", exc)
    if not isinstance(raw, dict):
        raise WsCommandError("internal", "CRM: invalid response when creating namespace", error_code='internal')
    name = raw.get("name")
    company_id = raw.get("company_id")
    if not isinstance(name, str) or not name.strip():
        raise WsCommandError("internal", "CRM: response has no name", error_code='internal')
    if not isinstance(company_id, str) or not company_id.strip():
        raise WsCommandError("internal", "CRM: response has no company_id", error_code='internal')
    description = raw.get("description")
    return OfficeNamespaceCreateResponse(
        name=name.strip(),
        company_id=company_id.strip(),
        description=description.strip() if isinstance(description, str) and description.strip() else None,
        is_default=bool(raw.get("is_default")),
    )


async def op_catalogs_list(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogListResponse:
    _ = payload, user
    scope = await namespace_scope(di)
    rows = await di.office_access_service.list_accessible_catalogs_with_file_counts(
        company_id=scope.company_id,
        namespace=scope.namespace,
        user_id=scope.user_id,
    )
    items: list[OfficeCatalogListItem] = []
    for catalog, file_count in rows:
        items.append(
            await _build_catalog_list_item(
                di,
                catalog=catalog,
                file_count=file_count,
                current_user_id=scope.user_id,
            )
        )
    return OfficeCatalogListResponse(items=items)


async def op_catalogs_ensure_path(
    payload: DocumentEnsureRequest,
    *,
    user: User,
    di: Di,
) -> DocumentEnsureResult:
    _ = user
    scope = await namespace_scope(di)
    if not payload.catalog_path:
        raise WsCommandError("ws_invalid_payload", "catalog_path is required", error_code="ws_invalid_payload")
    catalog = await di.document_tree_service.ensure_path(
        company_id=scope.company_id,
        namespace=scope.namespace,
        user_id=scope.user_id,
        parent_catalog_id=payload.parent_catalog_id,
        catalog_path=payload.catalog_path,
        company_visible=payload.company_visible,
    )
    return DocumentEnsureResult(catalog_id=catalog.catalog_id, catalog_path=list(payload.catalog_path))


async def op_catalogs_create(
    payload: OfficeCatalogCreateRequest,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogDetailResponse:
    _ = user
    scope = await namespace_scope(di)
    if payload.parent_catalog_id is not None:
        await _require_catalog_admin(di, payload.parent_catalog_id, scope.user_id)
    try:
        catalog = await di.document_tree_service.ensure_path(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            parent_catalog_id=payload.parent_catalog_id,
            catalog_path=[payload.title.strip()],
            company_visible=payload.company_visible,
        )
    except ValueError as exc:
        raise_not_found(exc, str(exc))
    return await _build_catalog_detail_response(
        di,
        catalog=catalog,
        current_user_id=scope.user_id,
    )


async def op_catalogs_item(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogDetailResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_view(di, payload.catalog_id, scope.user_id)
    catalog = await DocumentCatalog.catalog_in_namespace(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Catalog not found", error_code='not_found')
    return await _build_catalog_detail_response(
        di,
        catalog=catalog,
        current_user_id=scope.user_id,
    )


async def op_catalogs_items(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogItemsResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_view(di, payload.catalog_id, scope.user_id)
    catalog = await DocumentCatalog.catalog_in_namespace(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Catalog not found", error_code='not_found')
    children = await DocumentCatalog.children_page(
        company_id=scope.company_id,
        namespace=scope.namespace,
        parent_catalog_id=payload.catalog_id,
    )
    catalog_items: list[OfficeCatalogListItem] = []
    for child in children:
        child_allowed = await di.authz_service.can_view(
            AuthzObject.document_catalog(child.catalog_id),
            user_id=scope.user_id,
        )
        if not child_allowed:
            continue
        file_count = await FileRecord.count_in_catalog(child.catalog_id)
        catalog_items.append(
            await _build_catalog_list_item(
                di,
                catalog=child,
                file_count=file_count,
                current_user_id=scope.user_id,
            )
        )
    rows = await FileRecord.alive_in_catalog(
        company_id=scope.company_id,
        catalog_id=payload.catalog_id,
    )
    documents = await records_to_items(rows, di.catalog_rag_index_service)
    return OfficeCatalogItemsResponse(
        catalog_id=payload.catalog_id,
        catalogs=catalog_items,
        documents=documents,
    )


async def op_catalogs_update(
    payload: OfficeCatalogUpdatePayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogDetailResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    updated = await DocumentCatalog.catalog_in_namespace(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if updated is None:
        raise WsCommandError("not_found", "Catalog not found", error_code='not_found')
    if payload.title is not None:
        updated = await DocumentCatalog.set_title(updated, payload.title.strip())
    if payload.company_visible is not None:
        await di.office_access_service.set_catalog_company_visible(
            updated,
            company_visible=payload.company_visible,
        )
    return await _build_catalog_detail_response(
        di,
        catalog=updated,
        current_user_id=scope.user_id,
    )


async def op_catalogs_remove(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    catalog = await DocumentCatalog.catalog_in_namespace(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Catalog not found", error_code='not_found')
    if catalog.rag_index_enabled:
        try:
            await di.catalog_rag_index_service.disable(payload.catalog_id)
        except ServiceClientError as exc:
            raise_from_service_client("rag", exc)
        except ValueError as exc:
            raise_from_catalog_rag_value_error(exc)
    try:
        document_count = await FileRecord.count_in_catalog(payload.catalog_id)
        if document_count > 0:
            raise ValueError("Catalog contains documents")
        for trashed in await FileRecord.trashed_in_catalog(payload.catalog_id):
            _ = await di.files_service.delete(trashed.file_id)
            await di.office_access_service.sync_document_deleted(trashed.file_id)
        child_count = await DocumentCatalog.count_children(
            payload.catalog_id,
        )
        if child_count > 0:
            raise ValueError("Catalog contains subcatalogs")
        deleted = await DocumentCatalog.delete_in_namespace(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
        )
    except ValueError as exc:
        raise_conflict(exc, str(exc))
    if not deleted:
        raise WsCommandError("not_found", "Catalog not found", error_code='not_found')
    await di.office_access_service.sync_catalog_deleted(payload.catalog_id)


async def op_catalogs_rag_enable(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogRagIndexEnableResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    try:
        return await di.catalog_rag_index_service.enable(payload.catalog_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_disable(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogRagIndexDisableResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    try:
        await di.catalog_rag_index_service.disable(payload.catalog_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    return OfficeCatalogRagIndexDisableResponse()


async def op_catalogs_rag_rebuild(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogRagIndexRebuildResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    try:
        return await di.catalog_rag_index_service.rebuild_catalog(payload.catalog_id)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_status(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogRagIndexStatusResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_view(
        di, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    try:
        return await di.catalog_rag_index_service.get_status(payload.catalog_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_settings(
    payload: OfficeCatalogRagSettingsPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogRagIndexSettingsResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    body = OfficeCatalogRagIndexSettingsPatchRequest.model_validate(
        payload.model_dump(exclude={"catalog_id"})
    )
    try:
        return await di.catalog_rag_index_service.patch_rag_index_settings(
            payload.catalog_id,
            body,
        )
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_search(
    payload: OfficeCatalogRagSearchPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogSemanticSearchResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_view(
        di, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    body = OfficeCatalogSemanticSearchRequest.model_validate(
        payload.model_dump(exclude={"catalog_id"})
    )
    try:
        return await di.catalog_rag_index_service.search_catalog(
            payload.catalog_id,
            body,
        )
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_members_list(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogMembersResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_view(di, payload.catalog_id, scope.user_id)
    catalog = await DocumentCatalog.catalog_in_namespace(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Catalog not found", error_code='not_found')
    items = await _list_catalog_member_items(
        di,
        catalog_id=payload.catalog_id,
        company_id=scope.company_id,
        namespace=scope.namespace,
    )
    return OfficeCatalogMembersResponse(members=items)


async def op_catalogs_member_add(
    payload: OfficeCatalogMemberAddPayload,
    *,
    user: User,
    di: Di,
) -> OfficeCatalogMembersResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    try:
        await di.office_access_service.add_catalog_member(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
            user_id=payload.user_id.strip(),
            relation=_catalog_member_relation_to_authz(payload.relation),
        )
    except ValueError as exc:
        raise_invalid(exc)
    items = await _list_catalog_member_items(
        di,
        catalog_id=payload.catalog_id,
        company_id=scope.company_id,
        namespace=scope.namespace,
    )
    return OfficeCatalogMembersResponse(members=items)


async def op_catalogs_member_remove(
    payload: OfficeCatalogMemberRemovePayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_admin(di, payload.catalog_id, scope.user_id)
    catalog = await DocumentCatalog.catalog_in_namespace(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Catalog not found", error_code='not_found')
    try:
        await di.office_access_service.remove_catalog_member(
            payload.catalog_id,
            payload.member_user_id,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_catalogs_access(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_share(di, payload.catalog_id, scope.user_id)
    try:
        return await di.office_access_service.get_catalog_access(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
        )
    except ValueError as exc:
        raise_not_found(exc, str(exc))


async def op_catalogs_access_update(
    payload: OfficeCatalogAccessUpdatePayload,
    *,
    user: User,
    di: Di,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_share(di, payload.catalog_id, scope.user_id)
    body = OfficeResourceAccessPatchRequest.model_validate(
        payload.model_dump(exclude={"catalog_id", "origin"})
    )
    try:
        response, _raw_token = await di.office_access_service.patch_catalog_access(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
            body,
            payload.origin,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return response


async def op_catalogs_access_rotate_link(
    payload: OfficeCatalogAccessRotatePayload,
    *,
    user: User,
    di: Di,
) -> OfficeResourceAccessRotateLinkResponse:
    _ = user
    scope = await namespace_scope(di)
    await _require_catalog_share(di, payload.catalog_id, scope.user_id)
    try:
        return await di.office_access_service.rotate_catalog_link(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
            payload.origin,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_documents_list(
    payload: OfficeDocumentsListPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentListResponse:
    _ = user
    scope = await namespace_scope(di)
    seen: set[str] = set()
    resolved_ids: list[str] = []
    for raw_id in payload.catalog_ids:
        catalog_id = raw_id.strip()
        if catalog_id == "" or catalog_id in seen:
            continue
        seen.add(catalog_id)
        resolved_ids.append(catalog_id)
    if not resolved_ids:
        raise WsCommandError(
            "ws_invalid_payload",
            "Specify catalog_id or at least one catalog_ids value",
                  error_code='ws_invalid_payload',
              )
    for catalog_id in resolved_ids:
        await _require_catalog_view(
            di, catalog_id, scope.user_id, missing_as="forbidden"
        )
    rows: list[FileRecord] = []
    for catalog_id in resolved_ids:
        rows.extend(
            await FileRecord.alive_in_catalog(company_id=scope.company_id, catalog_id=catalog_id)
        )
    items = await records_to_items(rows, di.catalog_rag_index_service)
    if payload.q is not None and payload.q.strip() != "":
        needle = payload.q.strip().casefold()
        items = [item for item in items if needle in item.title.casefold()]
    items = _sort_office_document_items(items, payload.sort, payload.order)
    return OfficeDocumentListResponse(items=items)


async def op_documents_create_from_file(
    payload: OfficeDocumentFromFileRequest,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentCreateResponse:
    _ = user
    scope = await namespace_scope(di)
    file_id = payload.file_id.strip()
    meta = await di.files_service.get_optional(file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code='not_found')
    if meta.company_id != scope.company_id:
        raise WsCommandError("forbidden", "File does not belong to the company", error_code='forbidden')
    file_category, onlyoffice_document_type = resolve_binding_metadata(
        meta.original_name,
        (meta.content_type or "application/octet-stream").split(";")[0].strip(),
    )
    existing = await FileRecord.for_company(
        file_id,
        scope.company_id,
    )
    catalog_id = payload.catalog_id
    if (catalog_id is None or catalog_id.strip() == "") and existing is not None:
        catalog_id = existing.catalog_id
    resolved_catalog_id = await _resolve_catalog_for_create(
        di,
        user_id=scope.user_id,
        catalog_id=catalog_id,
    )
    if existing is not None and existing.catalog_id == resolved_catalog_id:
        await require_binding_catalog_access(di, existing, scope.user_id)
        category, office_type = _record_meta(existing)
        return OfficeDocumentCreateResponse(
            file_id=existing.file_id,
            catalog_id=_binding_catalog_id(existing),
            file_category=category,
            onlyoffice_document_type=office_type,
            title=document_title(existing),
            editor_url=editor_embed_url(existing.file_id, scope.namespace),
        )
    if existing is not None and existing.catalog_id is not None:
        await require_binding_catalog_access(di, existing, scope.user_id)
        existing.deleted_at = None
        existing.deleted_by_user_id = None
        row = await di.document_tree_service.move_file(
            existing,
            catalog_id=resolved_catalog_id,
            original_name=_document_name_with_source_extension(
                payload.title,
                meta.original_name,
            ),
            conflict="autorename",
            namespace=scope.namespace,
        )
        try:
            await index_binding_if_catalog_enabled(di, row)
        except ServiceClientError as exc:
            raise_from_service_client("rag", exc)
        except ValueError as exc:
            raise_from_catalog_rag_value_error(exc)
        category, office_type = _record_meta(row)
        return OfficeDocumentCreateResponse(
            file_id=row.file_id,
            catalog_id=resolved_catalog_id,
            file_category=category,
            onlyoffice_document_type=office_type,
            title=document_title(row),
            editor_url=editor_embed_url(row.file_id, scope.namespace),
        )
    update: dict[str, JsonValue] = {"deleted_at": None, "deleted_by_user_id": None}
    rename_to = _document_name_with_source_extension(payload.title, meta.original_name)
    if rename_to is not None:
        update["original_name"] = rename_to
    meta = meta.model_copy(update=update)
    placed = await di.document_tree_service.place(
        meta,
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(),
        placement=DocumentPlacement(catalog_id=resolved_catalog_id),
        namespace=scope.namespace,
        user_id=scope.user_id,
    )
    row = placed.record
    if row.catalog_id is None:
        raise WsCommandError("internal", "document was not placed in a catalog", error_code="internal")
    try:
        await index_binding_if_catalog_enabled(di, row)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    return OfficeDocumentCreateResponse(
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        file_category=file_category,
        onlyoffice_document_type=onlyoffice_document_type,
        title=document_title(row),
        editor_url=editor_embed_url(row.file_id, scope.namespace),
    )


async def op_documents_rag_statuses(
    payload: OfficeDocumentsRagIndexStatusesRequest,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentsRagIndexStatusesResponse:
    _ = user
    _ = await namespace_scope(di)
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in payload.file_ids:
        file_id = raw_id.strip()
        if file_id == "":
            raise WsCommandError("ws_invalid_payload", "file_ids must not contain empty values", error_code='ws_invalid_payload')
        if file_id in seen:
            continue
        seen.add(file_id)
        normalized_ids.append(file_id)
    if not normalized_ids:
        raise WsCommandError("ws_invalid_payload", "file_ids is required", error_code='ws_invalid_payload')
    statuses = await di.catalog_rag_index_service.batch_status_buckets(normalized_ids)
    return OfficeDocumentsRagIndexStatusesResponse(statuses=statuses)


async def op_documents_empty(
    payload: OfficeEmptyCreateRequest,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentCreateResponse:
    _ = user
    scope = await namespace_scope(di)
    settings = get_settings()
    if not settings.s3.enabled or not settings.s3.bucket_name:
        raise WsCommandError("internal", "S3 is not configured", error_code='internal')
    stem = _safe_filename_stem(payload.title)
    kind = payload.document_type
    if kind == "word":
        if not _EMPTY_DOCX.is_file():
            raise WsCommandError("internal", "Empty document template not found", error_code='internal')
        data = _EMPTY_DOCX.read_bytes()
        original_name = f"{stem}.docx"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        file_category = FileCategory.OFFICE_DOC.value
        onlyoffice_document_type = "word"
    elif kind == "cell":
        spreadsheet_format = payload.spreadsheet_format
        if spreadsheet_format == "csv":
            data = b"col1,col2\n"
            original_name = f"{stem}.csv"
            content_type = "text/csv"
        else:
            data = minimal_xlsx_bytes()
            original_name = f"{stem}.xlsx"
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        file_category = FileCategory.SPREADSHEET.value
        onlyoffice_document_type = "cell"
    else:
        data = minimal_pptx_bytes()
        original_name = f"{stem}.pptx"
        content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        file_category = FileCategory.PRESENTATION.value
        onlyoffice_document_type = "slide"
    resolved_catalog_id = await _resolve_catalog_for_create(
        di,
        user_id=scope.user_id,
        catalog_id=payload.catalog_id,
    )
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.OFFICE_DOCUMENT),
        placement=DocumentPlacement(catalog_id=resolved_catalog_id),
        post_create=FilePostCreate(is_public=False),
    )
    meta = await di.files_service.create(
        spec=spec,
        data=data,
        original_name=original_name,
        content_type=content_type,
    )
    if meta.catalog_id is None:
        raise WsCommandError("internal", "document was not placed in a catalog", error_code="internal")
    return OfficeDocumentCreateResponse(
        file_id=meta.file_id,
        catalog_id=meta.catalog_id,
        file_category=file_category,
        onlyoffice_document_type=onlyoffice_document_type,
        title=document_title(meta),
        editor_url=editor_embed_url(meta.file_id, scope.namespace),
    )


async def op_documents_editor_session(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentEditorSessionResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id, allow_deleted=True)
    await require_binding_catalog_access(di, row, scope.user_id)
    category, office_type = _record_meta(row)
    return OfficeDocumentEditorSessionResponse(
        file_id=row.file_id,
        catalog_id=row.catalog_id or "",
        title=document_title(row),
        file_category=category,
        onlyoffice_document_type=office_type,
        namespace=scope.namespace,
        editor_url=editor_embed_url(row.file_id, scope.namespace),
    )


async def _apply_document_bytes_mutation(
    *,
    file_id: str,
    di: Di,
    mutate: _DocumentBytesMutation,
    changed_count: int | None = None,
) -> OfficeDocumentMutationResponse:
    scope = await namespace_scope(di)
    async with document_mutation_lock(di, file_id):
        row = await load_binding(scope, file_id)
        await require_binding_catalog_access(di, row, scope.user_id)
        meta = await di.files_service.get_optional(row.file_id)
        if meta is None:
            raise WsCommandError("not_found", "File not found", error_code='not_found')
        caps = di.viewer_service.capabilities_for_file(
            file_category=_record_meta(row)[0],
            file_record=meta,
        )
        if not caps.server_mutations:
            raise WsCommandError(
                "ws_invalid_payload",
                "Server mutations are not available for this file type",
                      error_code='ws_invalid_payload',
                  )
        document_key = onlyoffice_document_key(row.file_id, meta.checksum)
        force_code = await force_save_open_editor_if_needed(
            file_id=row.file_id,
            document_key=document_key,
        )
        if force_code == 0:
            materialized = await wait_for_file_change_after_forcesave(
                di=di,
                file_id=row.file_id,
                previous_checksum=meta.checksum,
                previous_file_size=meta.file_size,
                max_iterations=6,
                raise_on_timeout=False,
            )
            if not materialized:
                logger.info("office.onlyoffice.forcesave.change.file.server", file_id=row.file_id)
            meta = await di.files_service.get_optional(row.file_id)
            if meta is None:
                raise WsCommandError("not_found", "File not found", error_code='not_found')
        if force_code in (0, 4):
            await drop_open_editor_sessions(
                file_id=row.file_id,
                document_key=document_key,
            )
        if meta.company_id is None or meta.company_id == "":
            raise WsCommandError("not_found", "File has no company", error_code="not_found")
        handle = await FileGate().open_record(
            meta,
            SystemPrincipal(company_id=meta.company_id),
        )
        current_bytes = await handle.read_bytes()
        try:
            mutation_result = mutate(current_bytes, meta.original_name)
        except DocumentMutationError as exc:
            raise WsCommandError("ws_invalid_payload", str(exc), error_code='ws_invalid_payload') from exc
        if isinstance(mutation_result, tuple):
            new_bytes, changed = mutation_result
        else:
            new_bytes, changed = mutation_result, changed_count
        if changed == 0:
            return OfficeDocumentMutationResponse(
                file_id=row.file_id,
                checksum=meta.checksum,
                file_size=meta.file_size,
                editor_url=editor_embed_url(row.file_id, scope.namespace),
                changed_count=0,
            )
        updated = await di.files_service.replace_content(
            meta,
            new_bytes,
            content_type=meta.content_type or "application/octet-stream",
            expected_checksum=meta.checksum,
        )
        return OfficeDocumentMutationResponse(
            file_id=row.file_id,
            checksum=updated.checksum,
            file_size=len(new_bytes),
            editor_url=editor_embed_url(row.file_id, scope.namespace),
            changed_count=changed,
        )


async def op_documents_replace_text(
    payload: OfficeDocumentReplaceTextPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentMutationResponse:
    _ = user
    return await _apply_document_bytes_mutation(
        file_id=payload.file_id,
        di=di,
        mutate=lambda data, original_name: replace_text_in_document(
            data=data,
            original_name=original_name,
            find=payload.find,
            replace=payload.replace,
            match_case=payload.match_case,
        ),
    )


async def op_documents_append_text(
    payload: OfficeDocumentAppendTextPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentMutationResponse:
    _ = user
    return await _apply_document_bytes_mutation(
        file_id=payload.file_id,
        di=di,
        mutate=lambda data, original_name: append_text_to_document(
            data=data,
            original_name=original_name,
            text=payload.text,
        ),
        changed_count=None,
    )


async def op_documents_update_cells(
    payload: OfficeDocumentUpdateCellsPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentMutationResponse:
    _ = user
    return await _apply_document_bytes_mutation(
        file_id=payload.file_id,
        di=di,
        mutate=lambda data, original_name: update_spreadsheet_cells(
            data=data,
            original_name=original_name,
            sheet=payload.sheet,
            cells=payload.cells,
        ),
        changed_count=None,
    )


async def op_documents_rename(
    payload: OfficeDocumentRenamePayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentRenameResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    updated = await di.document_tree_service.move_file(
        row,
        catalog_id=row.catalog_id or "",
        original_name=payload.title.strip(),
        conflict="fail",
        namespace=scope.namespace,
    )
    return OfficeDocumentRenameResponse(file_id=updated.file_id, title=document_title(updated))


async def op_documents_remove(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    try:
        await unindex_binding_from_catalog(di, _binding_catalog_id(row), row.file_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    if row.deleted_at is not None:
        raise WsCommandError("not_found", "Binding not found", error_code='not_found')
    now = datetime.now(timezone.utc)
    _ = await FileRecord.mark_trashed(row, user_id=scope.user_id, deleted_at=now)
    await OfficeDocumentEvent.record_document_event(
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="deleted",
        user_id=scope.user_id,
        payload={},
    )


async def op_documents_deleted_list(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentListResponse:
    _ = payload, user
    scope = await namespace_scope(di)
    catalogs = await DocumentCatalog.list_in_namespace(scope.company_id, scope.namespace)
    rows = await FileRecord.trashed_in_namespace(
        scope.company_id,
        [catalog.catalog_id for catalog in catalogs],
    )
    items = await records_to_items(rows, di.catalog_rag_index_service)
    return OfficeDocumentListResponse(items=items)


async def op_documents_restore(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentItem:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id, require_trashed=True)
    row = await FileRecord.clear_trash(row)
    await require_binding_catalog_access(di, row, scope.user_id)
    await OfficeDocumentEvent.record_document_event(
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="restored",
        user_id=scope.user_id,
        payload={},
    )
    try:
        await index_binding_if_catalog_enabled(di, row)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    restored = await records_to_items([row], di.catalog_rag_index_service)
    return restored[0]


async def op_documents_permanent_remove(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id, require_trashed=True)
    await _require_trashed_binding_access(di, row, scope.user_id)
    try:
        await unindex_binding_from_catalog(di, _binding_catalog_id(row), row.file_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    deleted = await di.files_service.delete(payload.file_id)
    if not deleted:
        raise WsCommandError("not_found", "Binding not found", error_code='not_found')
    await di.office_access_service.sync_document_deleted(payload.file_id)


async def op_documents_move(
    payload: OfficeDocumentMovePayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentItem:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    await _require_catalog_view(
        di, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    source_catalog_id = _binding_catalog_id(row)
    if row.deleted_at is not None:
        raise WsCommandError("not_found", "Binding not found", error_code='not_found')
    moved = await di.document_tree_service.move_file(
        row,
        catalog_id=payload.catalog_id,
        original_name=row.original_name,
        conflict="autorename",
        namespace=scope.namespace,
    )
    await di.office_access_service.sync_document_moved(
        moved,
        old_catalog_id=source_catalog_id,
    )
    await OfficeDocumentEvent.record_document_event(
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="moved",
        user_id=scope.user_id,
        payload={"catalog_id": payload.catalog_id},
    )
    try:
        await unindex_binding_from_catalog(di, source_catalog_id, row.file_id)
        await index_binding_if_catalog_enabled(di, moved)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    moved_items = await records_to_items([moved], di.catalog_rag_index_service)
    return moved_items[0]


async def op_documents_copy(
    payload: OfficeDocumentCopyPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentCreateResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    await _require_catalog_view(
        di, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    meta = await di.files_service.get_optional(row.file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code='not_found')
    if meta.company_id is None or meta.company_id == "":
        raise WsCommandError("not_found", "File has no company", error_code="not_found")
    handle = await FileGate().open_record(
        meta,
        SystemPrincipal(company_id=meta.company_id),
    )
    file_bytes = await handle.read_bytes()
    copy_title = payload.title.strip() if payload.title is not None else f"{row.original_name} (copy)"
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.OFFICE_DOCUMENT),
        placement=DocumentPlacement(catalog_id=payload.catalog_id),
        post_create=FilePostCreate(is_public=False),
    )
    created = await di.files_service.create(
        spec=spec,
        data=file_bytes,
        original_name=copy_title,
        content_type=meta.content_type,
        content_sha256_hex=hashlib.sha256(file_bytes).hexdigest(),
    )
    await OfficeDocumentEvent.record_document_event(
        file_id=created.file_id,
        company_id=scope.company_id,
        event_type="copied",
        user_id=scope.user_id,
        payload={"source_file_id": payload.file_id},
    )
    try:
        await index_binding_if_catalog_enabled(di, created)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    await _sync_document_created_or_rollback(
        di,
        created,
        owner_user_id=scope.user_id,
    )
    return OfficeDocumentCreateResponse(
        file_id=created.file_id,
        catalog_id=_binding_catalog_id(created),
        file_category=_record_meta(created)[0],
        onlyoffice_document_type=_record_meta(created)[1],
        title=document_title(created),
    )


async def op_documents_search(
    payload: OfficeDocumentSearchPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentListResponse:
    _ = user
    scope = await namespace_scope(di)
    needle = payload.q.strip()
    if needle == "":
        rows = []
    else:
        catalogs = await DocumentCatalog.list_in_namespace(scope.company_id, scope.namespace)
        rows = await FileRecord.search_alive(
            scope.company_id,
            [catalog.catalog_id for catalog in catalogs],
            needle,
            100,
        )
    items = await records_to_items(rows, di.catalog_rag_index_service)
    return OfficeDocumentListResponse(items=items)


async def op_documents_access(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    return await di.office_access_service.get_binding_access(row)


async def op_documents_access_update(
    payload: OfficeDocumentAccessUpdatePayload,
    *,
    user: User,
    di: Di,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    body = OfficeResourceAccessPatchRequest.model_validate(
        payload.model_dump(exclude={"file_id", "origin"})
    )
    try:
        response, _raw_token = await di.office_access_service.patch_binding_access(
            row,
            body,
            payload.origin,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return response


async def op_documents_access_rotate_link(
    payload: OfficeDocumentAccessRotatePayload,
    *,
    user: User,
    di: Di,
) -> OfficeResourceAccessRotateLinkResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    try:
        return await di.office_access_service.rotate_binding_link(row, payload.origin)
    except ValueError as exc:
        raise_invalid(exc)


async def op_documents_preview(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentPreviewResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    meta = await di.files_service.get_optional(row.file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code='not_found')
    preview_url = await di.viewer_service.preview_for_binding(binding=row, file_record=meta)
    return OfficeDocumentPreviewResponse(file_id=row.file_id, preview_url=preview_url)


async def op_documents_share_create(
    payload: OfficeDocumentShareCreatePayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentShareItem:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    permission = payload.permission
    patch_body = OfficeResourceAccessPatchRequest(
        link_enabled=True,
        link_permission=permission,
    )
    try:
        existing_link = await DocumentLink.for_target("file", row.file_id)
        if existing_link is not None and existing_link.enabled:
            rotated = await di.office_access_service.rotate_binding_link(
                row, payload.origin
            )
            public_url = rotated.public_url
        else:
            access_response, _raw_token = await di.office_access_service.patch_binding_access(
                row,
                patch_body,
                payload.origin,
            )
            if access_response.public_url is None:
                raise ValueError("Failed to create a public link")
            public_url = access_response.public_url
    except ValueError as exc:
        raise_invalid(exc)
    await OfficeDocumentEvent.record_document_event(
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="shared",
        user_id=scope.user_id,
        payload={"file_id": payload.file_id},
    )
    return OfficeDocumentShareItem(
        share_id=payload.file_id,
        file_id=payload.file_id,
        permission=permission,
        share_url=public_url,
        expires_at=None,
        created_at=datetime.now(timezone.utc),
    )


async def op_documents_shares_list(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[OfficeDocumentShareItem]:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    items: list[OfficeDocumentShareItem] = []
    share_link = await DocumentLink.for_target("file", row.file_id)
    if share_link is not None and share_link.enabled and share_link.token_hash is not None:
        if share_link.permission not in ("viewer", "editor"):
            raise WsCommandError(
                "ws_invalid_payload",
                f"Invalid link_permission: {share_link.permission}",
                      error_code='ws_invalid_payload',
                  )
        items.append(
            OfficeDocumentShareItem(
                share_id=payload.file_id,
                file_id=payload.file_id,
                permission=share_link.permission,
                share_url=None,
                expires_at=None,
                created_at=row.created_at,
            )
        )
    return ListResponse[OfficeDocumentShareItem](items=items)


async def op_documents_revisions_list(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[OfficeDocumentRevision]:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    revisions = await OfficeDocumentRevision.list_for_file(payload.file_id, limit=10)
    return ListResponse[OfficeDocumentRevision](items=revisions)


async def op_documents_revision_create(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentRevision:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    revision = await OfficeDocumentRevision.append_document_revision(
        file_id=payload.file_id,
        revision_file_id=row.file_id,
        created_by_user_id=scope.user_id,
    )
    await OfficeDocumentEvent.record_document_event(
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="revision_created",
        user_id=scope.user_id,
        payload={"revision_id": revision.revision_id},
    )
    return revision


async def op_documents_events_list(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[OfficeDocumentEvent]:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id, allow_deleted=True)
    await require_binding_catalog_access(di, row, scope.user_id)
    events = await OfficeDocumentEvent.list_for_file(payload.file_id, limit=50)
    return ListResponse[OfficeDocumentEvent](items=events)


async def op_documents_metadata(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentMetadataResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    return OfficeDocumentMetadataResponse(file_id=row.file_id)


async def op_documents_ai_summary(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentAiSummaryResponse:
    _ = user
    scope = await namespace_scope(di)
    row = await load_binding(scope, payload.file_id)
    await require_binding_catalog_access(di, row, scope.user_id)
    return OfficeDocumentAiSummaryResponse(
        file_id=row.file_id,
        summary="",
        enabled=False,
    )
