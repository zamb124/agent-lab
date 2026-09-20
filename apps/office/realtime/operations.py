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
from sqlalchemy.exc import IntegrityError

from apps.office.config import get_office_settings
from apps.office.container import OfficeContainer
from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
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
    OfficeNamespaceItem,
    OfficeNamespaceTemplateItem,
    OfficeResourceAccessPatchRequest,
    OfficeResourceAccessResponse,
    OfficeResourceAccessRotateLinkResponse,
    OfficeSpreadsheetUpdateCellsRequest,
)
from apps.office.services.document_lifecycle import (
    binding_to_item,
    bindings_to_items,
    record_document_event,
)
from apps.office.services.document_mutations import (
    DocumentMutationError,
    append_text_to_document,
    replace_text_in_document,
    update_spreadsheet_cells,
)
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from apps.office.services.minimal_ooxml import minimal_pptx_bytes, minimal_xlsx_bytes
from apps.office.services.viewer_service import integration_configured
from core.api.team import TeamMemberResponse
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation
from core.clients.onlyoffice import sign_onlyoffice_jwt_hs256
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.documents.placement import (
    DocsBindResult,
    DocsEnsurePathRequest,
    DocsEnsurePathResult,
    DocsPlacement,
)
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.s3_client import S3ClientFactory
from core.files.types import FileCategory
from core.http import get_httpx_client
from core.identity.flow_employee import (
    flow_employee_curator_user_ids,
    is_flow_employee,
    require_flow_employee_flow_id,
)
from core.logging import get_log_context, get_logger
from core.models.base import StrictBaseModel
from core.models.identity_models import User
from core.pagination import ListResponse, OffsetPage
from core.request_scope import CompanyScope, NamespaceScope, require_company, require_namespace
from core.types import JsonObject, parse_json_object, require_json_array
from core.websocket import WsCommandError

logger = get_logger(__name__)

_EMPTY_DOCX = Path(__file__).resolve().parent.parent / "templates" / "empty.docx"
_CRM_API_V1_PREFIX = "/crm/api/v1"
_LOCK_POLL_SECONDS = 2.0
OfficeDocumentSortKey = Literal["created_at", "title", "file_size", "updated_at"]
OfficeDocumentSortOrder = Literal["asc", "desc"]
_DocumentBytesMutation = Callable[[bytes, str], bytes | tuple[bytes, int]]

_ONLYOFFICE_COMMAND_ERROR_DETAILS = {
    1: "document key is missing or no open document with this key was found",
    2: "callback URL is not correct or is not reachable from Document Server",
    3: "internal Document Server error",
    4: "no changes were applied before forcesave",
    5: "command is not correct",
    6: "invalid Document Server JWT token",
}


class OfficeEmptyPayload(StrictBaseModel):
    pass


class OfficeNamespacesListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


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


def _not_found(exc: Exception, detail: str) -> Never:
    raise WsCommandError("not_found", detail) from exc


def _invalid(exc: Exception) -> Never:
    raise WsCommandError("ws_invalid_payload", str(exc)) from exc


def _forbidden(exc: PermissionError | AuthzDenied) -> Never:
    raise WsCommandError("forbidden", str(exc)) from exc


def _conflict(exc: Exception, detail: str) -> Never:
    raise WsCommandError("conflict", detail) from exc


async def _namespace_scope(container: OfficeContainer) -> NamespaceScope:
    return await require_namespace(container.namespace_service)


def _company_scope() -> CompanyScope:
    return require_company()


def raise_from_service_client(service: str, exc: ServiceClientError) -> Never:
    message = str(exc)
    match = re.match(r"HTTP (\d{3})", message)
    if match:
        code = int(match.group(1))
        if code == 404:
            raise WsCommandError("not_found", message) from exc
        if code == 403:
            raise WsCommandError("forbidden", message) from exc
        if 400 <= code < 500:
            raise WsCommandError("ws_invalid_payload", message) from exc
    raise WsCommandError(
        "internal",
        f"Сервис {service} недоступен или вернул ошибку: {message}",
    ) from exc


def raise_from_catalog_rag_value_error(exc: ValueError) -> Never:
    message = str(exc)
    if message == "Каталог не найден":
        raise WsCommandError("not_found", message) from exc
    if message in {
        "RAG-индекс для каталога не включён",
        "Нет проиндексированных каталогов для поиска",
    }:
        raise WsCommandError("conflict", message) from exc
    raise WsCommandError("ws_invalid_payload", message) from exc


async def index_binding_if_catalog_enabled(
    container: OfficeContainer,
    binding: OfficeDocumentBinding,
    *,
    scope_company_id: str | None = None,
    scope_workspace_namespace: str | None = None,
    scope_user_id: str | None = None,
) -> None:
    _ = await container.catalog_rag_index_service.index_binding(
        binding,
        scope_company_id=scope_company_id,
        scope_workspace_namespace=scope_workspace_namespace,
        scope_user_id=scope_user_id,
    )


async def index_binding_if_catalog_enabled_with_job_context(
    container: OfficeContainer,
    binding: OfficeDocumentBinding,
    *,
    company_id: str,
    workspace_namespace: str,
    user_id: str,
) -> None:
    normalized_company_id = company_id.strip()
    normalized_namespace = workspace_namespace.strip()
    normalized_user_id = user_id.strip()
    if normalized_company_id == "":
        raise ValueError("company_id обязателен")
    if normalized_namespace == "":
        raise ValueError("workspace_namespace обязателен")
    if normalized_user_id == "":
        raise ValueError("user_id обязателен")

    company = await container.company_repository.get(normalized_company_id)
    if company is None:
        raise ValueError(f"Компания не найдена: {normalized_company_id}")
    user = await container.user_repository.get(normalized_user_id)
    if user is None:
        raise ValueError(f"Пользователь не найден: {normalized_user_id}")

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
            container,
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
    container: OfficeContainer,
    catalog_id: str,
    file_id: str,
) -> None:
    await container.catalog_rag_index_service.unindex_binding(catalog_id, file_id)


async def _sync_catalog_created_or_rollback(
    container: OfficeContainer,
    catalog: OfficeDocumentCatalog,
    *,
    owner_user_id: str,
    company_visible: bool,
    company_id: str,
    namespace: str,
) -> None:
    try:
        await container.office_access_service.sync_catalog_created(
            catalog,
            owner_user_id=owner_user_id,
            company_visible=company_visible,
        )
    except Exception:
        _ = await container.catalog_repository.delete_catalog(
            catalog.catalog_id, company_id, namespace
        )
        raise


async def _sync_document_created_or_rollback(
    container: OfficeContainer,
    row: OfficeDocumentBinding,
    *,
    owner_user_id: str,
) -> None:
    try:
        await container.office_access_service.sync_document_created(
            row,
            owner_user_id=owner_user_id,
        )
    except Exception:
        _ = await container.document_binding_repository.delete_binding(
            row.file_id, row.company_id, row.namespace
        )
        raise


async def _require_catalog_view(
    container: OfficeContainer,
    catalog_id: str,
    user_id: str,
    *,
    missing_as: Literal["not_found", "forbidden"] = "not_found",
) -> None:
    allowed = await container.authz_service.can_view(
        AuthzObject.office_catalog(catalog_id),
        user_id=user_id,
    )
    if allowed:
        return
    if missing_as == "forbidden":
        raise WsCommandError("forbidden", "Нет доступа к каталогу")
    raise WsCommandError("not_found", "Каталог не найден")


async def _require_catalog_admin(
    container: OfficeContainer,
    catalog_id: str,
    user_id: str,
) -> None:
    try:
        await container.authz_service.require_can_admin(
            AuthzObject.office_catalog(catalog_id),
            user_id=user_id,
        )
    except AuthzDenied as exc:
        _forbidden(exc)


async def _require_catalog_share(
    container: OfficeContainer,
    catalog_id: str,
    user_id: str,
) -> None:
    try:
        await container.authz_service.require_relation(
            AuthzRelation.CAN_SHARE,
            AuthzObject.office_catalog(catalog_id),
            user_id=user_id,
        )
    except AuthzDenied as exc:
        _forbidden(exc)


async def _require_binding_catalog_access(
    container: OfficeContainer,
    row: OfficeDocumentBinding,
    user_id: str,
) -> None:
    allowed = await container.office_access_service.user_can_view_document(
        row,
        company_id=row.company_id,
        namespace=row.namespace,
        user_id=user_id,
    )
    if not allowed:
        raise WsCommandError("forbidden", "Нет доступа к каталогу документа")


async def _require_trashed_binding_access(
    container: OfficeContainer,
    row: OfficeDocumentBinding,
    user_id: str,
) -> None:
    allowed = await container.office_access_service.user_can_manage_trashed_binding(
        row,
        company_id=row.company_id,
        namespace=row.namespace,
        user_id=user_id,
    )
    if not allowed:
        raise WsCommandError("forbidden", "Нет доступа к каталогу документа")


async def _resolve_catalog_for_create(
    container: OfficeContainer,
    *,
    user_id: str,
    catalog_id: str | None,
) -> str:
    if catalog_id is None or catalog_id.strip() == "":
        raise WsCommandError("ws_invalid_payload", "Укажите catalog_id: сначала создайте каталог")
    cid = catalog_id.strip()
    allowed = await container.authz_service.can_view(
        AuthzObject.office_catalog(cid),
        user_id=user_id,
    )
    if not allowed:
        raise WsCommandError("forbidden", "Нет доступа к каталогу")
    return cid


async def _user_display(container: OfficeContainer, user_id: str) -> tuple[str, str | None]:
    user = await container.user_repository.get(user_id)
    if user is not None:
        return user.name or user_id, user.avatar_url
    return user_id, None


async def _build_catalog_detail_response(
    container: OfficeContainer,
    *,
    catalog: OfficeDocumentCatalog,
    current_user_id: str,
) -> OfficeCatalogDetailResponse:
    access = container.office_access_service
    owner_user_id = await access.resolve_catalog_owner_user_id(catalog.catalog_id)
    company_visible = await access.catalog_is_company_visible(
        catalog.catalog_id,
        catalog.company_id,
    )
    display_name, avatar_url = await _user_display(container, owner_user_id)
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
    container: OfficeContainer,
    *,
    catalog: OfficeDocumentCatalog,
    file_count: int,
    current_user_id: str,
) -> OfficeCatalogListItem:
    access = container.office_access_service
    owner_user_id = catalog.owner_user_id
    company_visible = await access.catalog_is_company_visible(
        catalog.catalog_id,
        catalog.company_id,
    )
    display_name, avatar_url = await _user_display(container, owner_user_id)
    rag_service = container.catalog_rag_index_service
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
    container: OfficeContainer,
    *,
    catalog_id: str,
    company_id: str,
    namespace: str,
) -> list[OfficeCatalogMemberItem]:
    access_response = await container.office_access_service.get_catalog_access(
        catalog_id,
        company_id,
        namespace,
    )
    items: list[OfficeCatalogMemberItem] = []
    for member in access_response.members:
        display_name, avatar_url = await _user_display(container, member.user_id)
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
    container: OfficeContainer,
    file_id: str,
    *,
    wait_timeout_seconds: float = 45.0,
):
    client = container.redis_client
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
                    raise WsCommandError("conflict", "Документ уже изменяется")
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
            "OnlyOffice command failed before mutation file_id=%s command=%s http_status=%s response=%s",
            file_id,
            command_name,
            exc.response.status_code,
            exc.response.text[:500],
        )
        raise WsCommandError("conflict", f"OnlyOffice {command_name} command failed") from exc
    except HTTPError as exc:
        logger.exception(
            "OnlyOffice command failed before mutation file_id=%s command=%s http_status=%s response=%s",
            file_id,
            command_name,
            None,
            "",
        )
        raise WsCommandError("conflict", f"OnlyOffice {command_name} command failed") from exc
    data = parse_json_object(response.content, "OnlyOffice command response")
    if "error" not in data:
        raise WsCommandError("conflict", f"OnlyOffice {command_name} returned invalid response")
    error_code = data["error"]
    if not isinstance(error_code, str | int):
        raise WsCommandError("conflict", f"OnlyOffice {command_name} returned invalid response")
    try:
        code = int(error_code)
    except ValueError:
        raise WsCommandError(
            "conflict", f"OnlyOffice {command_name} returned invalid response"
        ) from None
    if code != 0:
        logger.warning(
            "OnlyOffice command returned error file_id=%s command=%s code=%s detail=%s",
            file_id,
            command_name,
            code,
            _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error"),
        )
    else:
        logger.info(
            "OnlyOffice command accepted file_id=%s command=%s key=%s",
            file_id,
            command_name,
            key,
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
    detail = _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error")
    raise WsCommandError("conflict", f"OnlyOffice forcesave failed: error={code} ({detail})")


async def drop_open_editor_sessions(*, file_id: str, document_key: str) -> None:
    code = await post_onlyoffice_command(
        payload={"c": "drop", "key": document_key},
        file_id=file_id,
        command_name="drop",
    )
    if code is None or code in (0, 1):
        return
    detail = _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error")
    raise WsCommandError("conflict", f"OnlyOffice drop failed: error={code} ({detail})")


async def wait_for_file_change_after_forcesave(
    *,
    container: OfficeContainer,
    file_id: str,
    previous_checksum: str | None,
    previous_file_size: int | None,
    max_iterations: int = 90,
    raise_on_timeout: bool = True,
) -> bool:
    for _ in range(max_iterations):
        await asyncio.sleep(0.5)
        meta = await container.files_service.get_optional(file_id)
        if meta is None:
            raise WsCommandError("not_found", "Файл не найден")
        if meta.checksum != previous_checksum or meta.file_size != previous_file_size:
            logger.info(
                "OnlyOffice forcesave materialized file_id=%s old_size=%s new_size=%s",
                file_id,
                previous_file_size,
                meta.file_size,
            )
            return True
    logger.warning(
        "OnlyOffice forcesave callback did not update file file_id=%s old_size=%s old_checksum=%s",
        file_id,
        previous_file_size,
        previous_checksum,
    )
    if raise_on_timeout:
        raise WsCommandError("conflict", "Не удалось дождаться сохранения открытого редактора")
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


async def _load_binding(
    container: OfficeContainer,
    scope: NamespaceScope,
    file_id: str,
    *,
    allow_deleted: bool = False,
    require_trashed: bool = False,
) -> OfficeDocumentBinding:
    row = await container.document_binding_repository.get(
        file_id,
        scope.company_id,
        scope.namespace,
    )
    if row is None:
        raise WsCommandError("not_found", "Привязка не найдена")
    if require_trashed:
        if row.deleted_at is None:
            raise WsCommandError("not_found", "Привязка не найдена в корзине")
        return row
    if row.deleted_at is not None and not allow_deleted:
        raise WsCommandError("not_found", "Привязка не найдена")
    return row


async def op_integration_status(
    payload: OfficeEmptyPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeIntegrationStatusResponse:
    _ = payload, user, container
    configured, detail = integration_configured()
    return OfficeIntegrationStatusResponse(configured=configured, detail=detail)


async def op_namespaces_list(
    payload: OfficeNamespacesListPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OffsetPage[OfficeNamespaceItem]:
    _ = user
    _ = _company_scope()
    rows = await container.namespace_service.list_company_workspaces(limit=1000)
    items: list[OfficeNamespaceItem] = [
        OfficeNamespaceItem(name=namespace.name.strip(), is_default=bool(namespace.is_default))
        for namespace in rows
        if namespace.name and namespace.name.strip()
    ]
    sliced = items[payload.offset : payload.offset + payload.limit]
    return OffsetPage[OfficeNamespaceItem](
        items=sliced,
        total=len(items),
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_namespaces_templates(
    payload: OfficeEmptyPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OffsetPage[OfficeNamespaceTemplateItem]:
    _ = payload, user
    _ = _company_scope()
    path = f"{_CRM_API_V1_PREFIX}/namespaces/templates"
    try:
        raw = await container.service_client.get("crm", path)
    except ServiceClientError as exc:
        raise_from_service_client("crm", exc)
    raw_items_value = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(raw_items_value, list):
        raise WsCommandError("internal", "CRM: неверный формат списка шаблонов namespace")
    raw_items = require_json_array(raw_items_value, "crm.namespace_templates.items")
    out: list[OfficeNamespaceTemplateItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise WsCommandError("internal", "CRM: элемент шаблона namespace не объект")
        template_id = item.get("template_id")
        if not isinstance(template_id, str) or not template_id.strip():
            raise WsCommandError("internal", "CRM: у шаблона нет template_id")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise WsCommandError("internal", "CRM: у шаблона нет name")
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
    container: OfficeContainer,
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
        raw = await container.service_client.post("crm", path, json=body)
    except ServiceClientError as exc:
        raise_from_service_client("crm", exc)
    if not isinstance(raw, dict):
        raise WsCommandError("internal", "CRM: неверный ответ при создании namespace")
    name = raw.get("name")
    company_id = raw.get("company_id")
    if not isinstance(name, str) or not name.strip():
        raise WsCommandError("internal", "CRM: в ответе нет name")
    if not isinstance(company_id, str) or not company_id.strip():
        raise WsCommandError("internal", "CRM: в ответе нет company_id")
    description = raw.get("description")
    return OfficeNamespaceCreateResponse(
        name=name.strip(),
        company_id=company_id.strip(),
        description=description.strip() if isinstance(description, str) and description.strip() else None,
        is_default=bool(raw.get("is_default")),
    )


async def op_company_members_list(
    payload: OfficeEmptyPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> ListResponse[TeamMemberResponse]:
    _ = payload, user
    scope = _company_scope()
    company = await container.company_repository.get(scope.company_id)
    if company is None:
        raise WsCommandError("not_found", "Компания не найдена")
    users_by_id = await container.user_repository.get_many(list(company.members.keys()))
    members: list[TeamMemberResponse] = []
    for member_user_id, roles in company.members.items():
        member_user = users_by_id.get(member_user_id)
        if member_user is None:
            continue
        member_email = member_user.emails[0] if member_user.emails else None
        member_is_employee = is_flow_employee(member_user)
        members.append(
            TeamMemberResponse(
                user_id=member_user_id,
                name=member_user.name,
                email=member_email,
                roles=roles,
                joined_at=member_user.created_at,
                avatar_url=member_user.avatar_url,
                is_flow_employee=member_is_employee,
                flow_id=require_flow_employee_flow_id(member_user) if member_is_employee else None,
                curator_user_ids=flow_employee_curator_user_ids(member_user) if member_is_employee else [],
            )
        )
    return ListResponse[TeamMemberResponse](items=members)


async def op_catalogs_list(
    payload: OfficeEmptyPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogListResponse:
    _ = payload, user
    scope = await _namespace_scope(container)
    rows = await container.office_access_service.list_accessible_catalogs_with_file_counts(
        company_id=scope.company_id,
        namespace=scope.namespace,
        user_id=scope.user_id,
    )
    items: list[OfficeCatalogListItem] = []
    for catalog, file_count in rows:
        items.append(
            await _build_catalog_list_item(
                container,
                catalog=catalog,
                file_count=file_count,
                current_user_id=scope.user_id,
            )
        )
    return OfficeCatalogListResponse(items=items)


async def op_catalogs_ensure_path(
    payload: DocsEnsurePathRequest,
    *,
    user: User,
    container: OfficeContainer,
) -> DocsEnsurePathResult:
    _ = user
    scope = await _namespace_scope(container)
    if not payload.path_segments:
        raise WsCommandError("ws_invalid_payload", "path_segments required")
    catalog_id = await container.docs_placement_service.ensure_catalog_path(
        company_id=scope.company_id,
        namespace=scope.namespace,
        segments=payload.path_segments,
        user_id=scope.user_id,
    )
    return DocsEnsurePathResult(catalog_id=catalog_id, catalog_path=list(payload.path_segments))


async def op_catalogs_create(
    payload: OfficeCatalogCreateRequest,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogDetailResponse:
    _ = user
    scope = await _namespace_scope(container)
    if payload.parent_catalog_id is not None:
        await _require_catalog_admin(container, payload.parent_catalog_id, scope.user_id)
    try:
        catalog = await container.catalog_repository.create(
            company_id=scope.company_id,
            namespace=scope.namespace,
            title=payload.title,
            owner_user_id=scope.user_id,
            parent_catalog_id=payload.parent_catalog_id,
        )
    except ValueError as exc:
        _not_found(exc, str(exc))
    await _sync_catalog_created_or_rollback(
        container,
        catalog,
        owner_user_id=scope.user_id,
        company_visible=payload.company_visible,
        company_id=scope.company_id,
        namespace=scope.namespace,
    )
    return await _build_catalog_detail_response(
        container,
        catalog=catalog,
        current_user_id=scope.user_id,
    )


async def op_catalogs_item(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogDetailResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_view(container, payload.catalog_id, scope.user_id)
    catalog = await container.catalog_repository.get(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Каталог не найден")
    return await _build_catalog_detail_response(
        container,
        catalog=catalog,
        current_user_id=scope.user_id,
    )


async def op_catalogs_items(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogItemsResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_view(container, payload.catalog_id, scope.user_id)
    catalog = await container.catalog_repository.get(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Каталог не найден")
    children = await container.catalog_repository.list_children(
        company_id=scope.company_id,
        namespace=scope.namespace,
        parent_catalog_id=payload.catalog_id,
    )
    catalog_items: list[OfficeCatalogListItem] = []
    for child in children:
        child_allowed = await container.authz_service.can_view(
            AuthzObject.office_catalog(child.catalog_id),
            user_id=scope.user_id,
        )
        if not child_allowed:
            continue
        file_count = await container.catalog_repository.count_documents(child.catalog_id)
        catalog_items.append(
            await _build_catalog_list_item(
                container,
                catalog=child,
                file_count=file_count,
                current_user_id=scope.user_id,
            )
        )
    rows = await container.document_binding_repository.list_by_company_namespace_and_catalog(
        scope.company_id,
        scope.namespace,
        payload.catalog_id,
    )
    documents = await bindings_to_items(container, rows)
    return OfficeCatalogItemsResponse(
        catalog_id=payload.catalog_id,
        catalogs=catalog_items,
        documents=documents,
    )


async def op_catalogs_update(
    payload: OfficeCatalogUpdatePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogDetailResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    updated = await container.catalog_repository.update_catalog(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
        title=payload.title,
    )
    if updated is None:
        raise WsCommandError("not_found", "Каталог не найден")
    if payload.company_visible is not None:
        await container.office_access_service.set_catalog_company_visible(
            updated,
            company_visible=payload.company_visible,
        )
    return await _build_catalog_detail_response(
        container,
        catalog=updated,
        current_user_id=scope.user_id,
    )


async def op_catalogs_remove(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> None:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    catalog = await container.catalog_repository.get(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Каталог не найден")
    if catalog.rag_index_enabled:
        try:
            await container.catalog_rag_index_service.disable(payload.catalog_id)
        except ServiceClientError as exc:
            raise_from_service_client("rag", exc)
        except ValueError as exc:
            raise_from_catalog_rag_value_error(exc)
    try:
        deleted = await container.catalog_repository.delete_catalog(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
        )
    except ValueError as exc:
        _conflict(exc, str(exc))
    if not deleted:
        raise WsCommandError("not_found", "Каталог не найден")
    await container.office_access_service.sync_catalog_deleted(payload.catalog_id)


async def op_catalogs_rag_enable(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogRagIndexEnableResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    try:
        return await container.catalog_rag_index_service.enable(payload.catalog_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_disable(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogRagIndexDisableResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    try:
        await container.catalog_rag_index_service.disable(payload.catalog_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    return OfficeCatalogRagIndexDisableResponse()


async def op_catalogs_rag_rebuild(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogRagIndexRebuildResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    try:
        return await container.catalog_rag_index_service.rebuild_catalog(payload.catalog_id)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_status(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogRagIndexStatusResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_view(
        container, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    try:
        return await container.catalog_rag_index_service.get_status(payload.catalog_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_settings(
    payload: OfficeCatalogRagSettingsPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogRagIndexSettingsResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    body = OfficeCatalogRagIndexSettingsPatchRequest.model_validate(
        payload.model_dump(exclude={"catalog_id"})
    )
    try:
        return await container.catalog_rag_index_service.patch_rag_index_settings(
            payload.catalog_id,
            body,
        )
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)


async def op_catalogs_rag_search(
    payload: OfficeCatalogRagSearchPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogSemanticSearchResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_view(
        container, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    body = OfficeCatalogSemanticSearchRequest.model_validate(
        payload.model_dump(exclude={"catalog_id"})
    )
    try:
        return await container.catalog_rag_index_service.search_catalog(
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
    container: OfficeContainer,
) -> OfficeCatalogMembersResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_view(container, payload.catalog_id, scope.user_id)
    catalog = await container.catalog_repository.get(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Каталог не найден")
    items = await _list_catalog_member_items(
        container,
        catalog_id=payload.catalog_id,
        company_id=scope.company_id,
        namespace=scope.namespace,
    )
    return OfficeCatalogMembersResponse(members=items)


async def op_catalogs_member_add(
    payload: OfficeCatalogMemberAddPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeCatalogMembersResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    try:
        await container.office_access_service.add_catalog_member(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
            user_id=payload.user_id.strip(),
            relation=_catalog_member_relation_to_authz(payload.relation),
        )
    except ValueError as exc:
        _invalid(exc)
    items = await _list_catalog_member_items(
        container,
        catalog_id=payload.catalog_id,
        company_id=scope.company_id,
        namespace=scope.namespace,
    )
    return OfficeCatalogMembersResponse(members=items)


async def op_catalogs_member_remove(
    payload: OfficeCatalogMemberRemovePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> None:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_admin(container, payload.catalog_id, scope.user_id)
    catalog = await container.catalog_repository.get(
        payload.catalog_id,
        scope.company_id,
        scope.namespace,
    )
    if catalog is None:
        raise WsCommandError("not_found", "Каталог не найден")
    try:
        await container.office_access_service.remove_catalog_member(
            payload.catalog_id,
            payload.member_user_id,
        )
    except ValueError as exc:
        _invalid(exc)


async def op_catalogs_access(
    payload: OfficeCatalogIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_share(container, payload.catalog_id, scope.user_id)
    try:
        return await container.office_access_service.get_catalog_access(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
        )
    except ValueError as exc:
        _not_found(exc, str(exc))


async def op_catalogs_access_update(
    payload: OfficeCatalogAccessUpdatePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_share(container, payload.catalog_id, scope.user_id)
    body = OfficeResourceAccessPatchRequest.model_validate(
        payload.model_dump(exclude={"catalog_id", "origin"})
    )
    try:
        response, _raw_token = await container.office_access_service.patch_catalog_access(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
            body,
            payload.origin,
        )
    except ValueError as exc:
        _invalid(exc)
    return response


async def op_catalogs_access_rotate_link(
    payload: OfficeCatalogAccessRotatePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeResourceAccessRotateLinkResponse:
    _ = user
    scope = await _namespace_scope(container)
    await _require_catalog_share(container, payload.catalog_id, scope.user_id)
    try:
        return await container.office_access_service.rotate_catalog_link(
            payload.catalog_id,
            scope.company_id,
            scope.namespace,
            payload.origin,
        )
    except ValueError as exc:
        _invalid(exc)


async def op_documents_list(
    payload: OfficeDocumentsListPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentListResponse:
    _ = user
    scope = await _namespace_scope(container)
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
            "Укажите catalog_id или хотя бы одно значение catalog_ids",
        )
    for catalog_id in resolved_ids:
        await _require_catalog_view(
            container, catalog_id, scope.user_id, missing_as="forbidden"
        )
    rows = await container.document_binding_repository.list_by_company_namespace_and_catalogs(
        scope.company_id,
        scope.namespace,
        resolved_ids,
    )
    items = await bindings_to_items(container, rows)
    if payload.q is not None and payload.q.strip() != "":
        needle = payload.q.strip().casefold()
        items = [item for item in items if needle in item.title.casefold()]
    items = _sort_office_document_items(items, payload.sort, payload.order)
    return OfficeDocumentListResponse(items=items)


async def op_documents_create_from_file(
    payload: OfficeDocumentFromFileRequest,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentCreateResponse:
    _ = user
    scope = await _namespace_scope(container)
    file_id = payload.file_id.strip()
    meta = await container.files_service.get_optional(file_id)
    if meta is None:
        raise WsCommandError("not_found", "Файл не найден")
    if meta.company_id != scope.company_id:
        raise WsCommandError("forbidden", "Файл не принадлежит компании")
    file_category, onlyoffice_document_type = resolve_binding_metadata(
        meta.original_name,
        (meta.content_type or "application/octet-stream").split(";")[0].strip(),
    )
    existing = await container.document_binding_repository.get_by_file_and_company(
        file_id,
        scope.company_id,
    )
    if existing is not None:
        await _require_binding_catalog_access(container, existing, scope.user_id)
        return OfficeDocumentCreateResponse(
            file_id=existing.file_id,
            catalog_id=existing.catalog_id,
            file_category=existing.file_category,
            onlyoffice_document_type=existing.onlyoffice_document_type,
            title=existing.title,
            editor_url=editor_embed_url(existing.file_id, scope.namespace),
        )
    resolved_catalog_id = await _resolve_catalog_for_create(
        container,
        user_id=scope.user_id,
        catalog_id=payload.catalog_id,
    )
    title = (payload.title or "").strip() or Path(meta.original_name).stem or meta.original_name
    try:
        row = await container.document_binding_repository.create(
            company_id=scope.company_id,
            namespace=scope.namespace,
            catalog_id=resolved_catalog_id,
            file_id=meta.file_id,
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            title=title,
            created_by_user_id=scope.user_id,
        )
    except IntegrityError:
        existing = await container.document_binding_repository.get_by_file_and_company(
            file_id,
            scope.company_id,
        )
        if existing is None:
            raise
        await _require_binding_catalog_access(container, existing, scope.user_id)
        return OfficeDocumentCreateResponse(
            file_id=existing.file_id,
            catalog_id=existing.catalog_id,
            file_category=existing.file_category,
            onlyoffice_document_type=existing.onlyoffice_document_type,
            title=existing.title,
            editor_url=editor_embed_url(existing.file_id, scope.namespace),
        )
    try:
        await index_binding_if_catalog_enabled(container, row)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    await _sync_document_created_or_rollback(
        container,
        row,
        owner_user_id=scope.user_id,
    )
    return OfficeDocumentCreateResponse(
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        title=row.title,
        editor_url=editor_embed_url(row.file_id, scope.namespace),
    )


async def op_documents_bind(
    payload: DocsPlacement,
    *,
    user: User,
    container: OfficeContainer,
) -> DocsBindResult:
    _ = user
    scope = _company_scope()
    return await container.docs_placement_service.bind(
        payload,
        company_id=scope.company_id,
        user_id=scope.user_id,
    )


async def op_documents_rag_statuses(
    payload: OfficeDocumentsRagIndexStatusesRequest,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentsRagIndexStatusesResponse:
    _ = user
    _ = await _namespace_scope(container)
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in payload.file_ids:
        file_id = raw_id.strip()
        if file_id == "":
            raise WsCommandError("ws_invalid_payload", "file_ids не должен содержать пустые значения")
        if file_id in seen:
            continue
        seen.add(file_id)
        normalized_ids.append(file_id)
    if not normalized_ids:
        raise WsCommandError("ws_invalid_payload", "file_ids обязателен")
    statuses = await container.catalog_rag_index_service.batch_status_buckets(normalized_ids)
    return OfficeDocumentsRagIndexStatusesResponse(statuses=statuses)


async def op_documents_empty(
    payload: OfficeEmptyCreateRequest,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentCreateResponse:
    _ = user
    scope = await _namespace_scope(container)
    settings = get_settings()
    if not settings.s3.enabled or not settings.s3.default_bucket:
        raise WsCommandError("internal", "S3 не настроен")
    stem = _safe_filename_stem(payload.title)
    kind = payload.document_type
    if kind == "word":
        if not _EMPTY_DOCX.is_file():
            raise WsCommandError("internal", "Шаблон пустого документа не найден")
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
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(entity_id=scope.namespace),
        retention=default_retention_for_source(FileSourceKind.OFFICE_DOCUMENT),
        post_create=FilePostCreate(is_public=False),
    )
    meta = await container.files_service.create(
        spec=spec,
        data=data,
        original_name=original_name,
        content_type=content_type,
    )
    resolved_catalog_id = await _resolve_catalog_for_create(
        container,
        user_id=scope.user_id,
        catalog_id=payload.catalog_id,
    )
    row = await container.document_binding_repository.create(
        company_id=scope.company_id,
        namespace=scope.namespace,
        catalog_id=resolved_catalog_id,
        file_id=meta.file_id,
        file_category=file_category,
        onlyoffice_document_type=onlyoffice_document_type,
        title=payload.title.strip(),
        created_by_user_id=scope.user_id,
    )
    try:
        await index_binding_if_catalog_enabled(container, row)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    await _sync_document_created_or_rollback(
        container,
        row,
        owner_user_id=scope.user_id,
    )
    return OfficeDocumentCreateResponse(
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        title=row.title,
        editor_url=editor_embed_url(row.file_id, scope.namespace),
    )


async def op_documents_editor_session(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentEditorSessionResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id, allow_deleted=True)
    await _require_binding_catalog_access(container, row, scope.user_id)
    return OfficeDocumentEditorSessionResponse(
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        title=row.title,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        namespace=scope.namespace,
        editor_url=editor_embed_url(row.file_id, scope.namespace),
    )


async def _apply_document_bytes_mutation(
    *,
    file_id: str,
    container: OfficeContainer,
    mutate: _DocumentBytesMutation,
    changed_count: int | None = None,
) -> OfficeDocumentMutationResponse:
    scope = await _namespace_scope(container)
    async with document_mutation_lock(container, file_id):
        row = await _load_binding(container, scope, file_id)
        await _require_binding_catalog_access(container, row, scope.user_id)
        meta = await container.files_service.get_optional(row.file_id)
        if meta is None:
            raise WsCommandError("not_found", "Файл не найден")
        caps = container.viewer_service.capabilities_for_file(
            file_category=row.file_category,
            file_record=meta,
        )
        if not caps.server_mutations:
            raise WsCommandError(
                "ws_invalid_payload",
                "Серверные мутации недоступны для этого типа файла",
            )
        document_key = onlyoffice_document_key(row.file_id, meta.checksum)
        force_code = await force_save_open_editor_if_needed(
            file_id=row.file_id,
            document_key=document_key,
        )
        if force_code == 0:
            materialized = await wait_for_file_change_after_forcesave(
                container=container,
                file_id=row.file_id,
                previous_checksum=meta.checksum,
                previous_file_size=meta.file_size,
                max_iterations=6,
                raise_on_timeout=False,
            )
            if not materialized:
                logger.info(
                    "OnlyOffice forcesave did not change file before server mutation; continuing file_id=%s",
                    row.file_id,
                )
            meta = await container.files_service.get_optional(row.file_id)
            if meta is None:
                raise WsCommandError("not_found", "Файл не найден")
        if force_code in (0, 4):
            await drop_open_editor_sessions(
                file_id=row.file_id,
                document_key=document_key,
            )
        s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
        try:
            current_bytes = await s3.download_bytes(meta.s3_key)
        finally:
            await s3.close()
        try:
            mutation_result = mutate(current_bytes, meta.original_name)
        except DocumentMutationError as exc:
            raise WsCommandError("ws_invalid_payload", str(exc)) from exc
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
        digest = hashlib.sha256(new_bytes).hexdigest()
        s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
        try:
            _ = await s3.upload_bytes(
                data=new_bytes,
                key=meta.s3_key,
                content_type=meta.content_type or "application/octet-stream",
                public=meta.is_public,
            )
        finally:
            await s3.close()
        updated_meta = meta.model_copy(
            update={"file_size": len(new_bytes), "checksum": digest},
        )
        _ = await container.files_service.save(updated_meta)
        return OfficeDocumentMutationResponse(
            file_id=row.file_id,
            checksum=digest,
            file_size=len(new_bytes),
            editor_url=editor_embed_url(row.file_id, scope.namespace),
            changed_count=changed,
        )


async def op_documents_replace_text(
    payload: OfficeDocumentReplaceTextPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentMutationResponse:
    _ = user
    return await _apply_document_bytes_mutation(
        file_id=payload.file_id,
        container=container,
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
    container: OfficeContainer,
) -> OfficeDocumentMutationResponse:
    _ = user
    return await _apply_document_bytes_mutation(
        file_id=payload.file_id,
        container=container,
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
    container: OfficeContainer,
) -> OfficeDocumentMutationResponse:
    _ = user
    return await _apply_document_bytes_mutation(
        file_id=payload.file_id,
        container=container,
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
    container: OfficeContainer,
) -> OfficeDocumentRenameResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    updated = await container.document_binding_repository.update_title(
        payload.file_id,
        scope.company_id,
        scope.namespace,
        payload.title.strip(),
    )
    if updated is None:
        raise WsCommandError("not_found", "Привязка не найдена")
    return OfficeDocumentRenameResponse(file_id=updated.file_id, title=updated.title)


async def op_documents_remove(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> None:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    try:
        await unindex_binding_from_catalog(container, row.catalog_id, row.file_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    deleted = await container.document_binding_repository.soft_delete(
        payload.file_id,
        scope.company_id,
        scope.namespace,
        scope.user_id,
    )
    if not deleted:
        raise WsCommandError("not_found", "Привязка не найдена")
    await record_document_event(
        container,
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="deleted",
        user_id=scope.user_id,
    )


async def op_documents_deleted_list(
    payload: OfficeEmptyPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentListResponse:
    _ = payload, user
    scope = await _namespace_scope(container)
    rows = await container.document_binding_repository.list_deleted_by_namespace(
        scope.company_id,
        scope.namespace,
    )
    items = await bindings_to_items(container, rows)
    return OfficeDocumentListResponse(items=items)


async def op_documents_restore(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentItem:
    _ = user
    scope = await _namespace_scope(container)
    row = await container.document_binding_repository.restore(
        payload.file_id,
        scope.company_id,
        scope.namespace,
    )
    if row is None:
        raise WsCommandError("not_found", "Привязка не найдена в корзине")
    await _require_binding_catalog_access(container, row, scope.user_id)
    await record_document_event(
        container,
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="restored",
        user_id=scope.user_id,
    )
    try:
        await index_binding_if_catalog_enabled(container, row)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    return await binding_to_item(container, row)


async def op_documents_permanent_remove(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> None:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id, require_trashed=True)
    await _require_trashed_binding_access(container, row, scope.user_id)
    try:
        await unindex_binding_from_catalog(container, row.catalog_id, row.file_id)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    deleted = await container.document_binding_repository.delete_binding(
        payload.file_id,
        scope.company_id,
        scope.namespace,
    )
    if not deleted:
        raise WsCommandError("not_found", "Привязка не найдена")
    await container.office_access_service.sync_document_deleted(payload.file_id)


async def op_documents_move(
    payload: OfficeDocumentMovePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentItem:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    await _require_catalog_view(
        container, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    source_catalog_id = row.catalog_id
    moved = await container.document_binding_repository.move_to_catalog(
        payload.file_id,
        scope.company_id,
        scope.namespace,
        payload.catalog_id,
    )
    if moved is None:
        raise WsCommandError("not_found", "Привязка не найдена")
    await container.office_access_service.sync_document_moved(
        moved,
        old_catalog_id=source_catalog_id,
    )
    await record_document_event(
        container,
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="moved",
        user_id=scope.user_id,
        payload={"catalog_id": payload.catalog_id},
    )
    try:
        await unindex_binding_from_catalog(container, source_catalog_id, row.file_id)
        await index_binding_if_catalog_enabled(container, moved)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    return await binding_to_item(container, moved)


async def op_documents_copy(
    payload: OfficeDocumentCopyPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentCreateResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    await _require_catalog_view(
        container, payload.catalog_id, scope.user_id, missing_as="forbidden"
    )
    meta = await container.files_service.get_optional(row.file_id)
    if meta is None:
        raise WsCommandError("not_found", "Файл не найден")
    s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
    try:
        file_bytes = await s3.download_bytes(meta.s3_key)
    finally:
        await s3.close()
    copy_title = payload.title.strip() if payload.title is not None else f"{row.title} (copy)"
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(entity_id=scope.namespace),
        retention=default_retention_for_source(FileSourceKind.OFFICE_DOCUMENT),
        post_create=FilePostCreate(is_public=False),
    )
    copied_file = await container.files_service.create(
        spec=spec,
        data=file_bytes,
        original_name=meta.original_name,
        content_type=meta.content_type,
        content_sha256_hex=hashlib.sha256(file_bytes).hexdigest(),
    )
    created = await container.document_binding_repository.create(
        company_id=scope.company_id,
        namespace=scope.namespace,
        catalog_id=payload.catalog_id,
        file_id=copied_file.file_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        title=copy_title,
        created_by_user_id=scope.user_id,
    )
    await record_document_event(
        container,
        file_id=created.file_id,
        company_id=scope.company_id,
        event_type="copied",
        user_id=scope.user_id,
        payload={"source_file_id": payload.file_id},
    )
    try:
        await index_binding_if_catalog_enabled(container, created)
    except ServiceClientError as exc:
        raise_from_service_client("rag", exc)
    except ValueError as exc:
        raise_from_catalog_rag_value_error(exc)
    await _sync_document_created_or_rollback(
        container,
        created,
        owner_user_id=scope.user_id,
    )
    return OfficeDocumentCreateResponse(
        file_id=created.file_id,
        catalog_id=created.catalog_id,
        file_category=created.file_category,
        onlyoffice_document_type=created.onlyoffice_document_type,
        title=created.title,
    )


async def op_documents_search(
    payload: OfficeDocumentSearchPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentListResponse:
    _ = user
    scope = await _namespace_scope(container)
    rows = await container.document_binding_repository.search_by_title(
        scope.company_id,
        scope.namespace,
        payload.q,
    )
    items = await bindings_to_items(container, rows)
    return OfficeDocumentListResponse(items=items)


async def op_documents_access(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    return await container.office_access_service.get_binding_access(row)


async def op_documents_access_update(
    payload: OfficeDocumentAccessUpdatePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeResourceAccessResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    body = OfficeResourceAccessPatchRequest.model_validate(
        payload.model_dump(exclude={"file_id", "origin"})
    )
    try:
        response, _raw_token = await container.office_access_service.patch_binding_access(
            row,
            body,
            payload.origin,
        )
    except ValueError as exc:
        _invalid(exc)
    return response


async def op_documents_access_rotate_link(
    payload: OfficeDocumentAccessRotatePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeResourceAccessRotateLinkResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    try:
        return await container.office_access_service.rotate_binding_link(row, payload.origin)
    except ValueError as exc:
        _invalid(exc)


async def op_documents_preview(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentPreviewResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    meta = await container.files_service.get_optional(row.file_id)
    if meta is None:
        raise WsCommandError("not_found", "Файл не найден")
    preview_url = await container.viewer_service.preview_for_binding(binding=row, file_record=meta)
    return OfficeDocumentPreviewResponse(file_id=row.file_id, preview_url=preview_url)


async def op_documents_share_create(
    payload: OfficeDocumentShareCreatePayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentShareItem:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    permission = payload.permission
    patch_body = OfficeResourceAccessPatchRequest(
        link_enabled=True,
        link_permission=permission,
    )
    try:
        if row.link_enabled:
            rotated = await container.office_access_service.rotate_binding_link(
                row, payload.origin
            )
            public_url = rotated.public_url
        else:
            access_response, _raw_token = await container.office_access_service.patch_binding_access(
                row,
                patch_body,
                payload.origin,
            )
            if access_response.public_url is None:
                raise ValueError("Не удалось создать публичную ссылку")
            public_url = access_response.public_url
    except ValueError as exc:
        _invalid(exc)
    await record_document_event(
        container,
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
    container: OfficeContainer,
) -> ListResponse[OfficeDocumentShareItem]:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    items: list[OfficeDocumentShareItem] = []
    if row.link_enabled and row.link_token_hash is not None:
        if row.link_permission not in ("viewer", "editor"):
            raise WsCommandError(
                "ws_invalid_payload",
                f"Invalid link_permission: {row.link_permission}",
            )
        items.append(
            OfficeDocumentShareItem(
                share_id=payload.file_id,
                file_id=payload.file_id,
                permission=row.link_permission,
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
    container: OfficeContainer,
) -> ListResponse[OfficeDocumentRevisionItem]:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    revisions = await container.document_revision_repository.list_for_file(payload.file_id)
    return ListResponse[OfficeDocumentRevisionItem](
        items=[
            OfficeDocumentRevisionItem(
                revision_id=revision.revision_id,
                revision_number=revision.revision_number,
                file_id=revision.file_id,
                created_by_user_id=revision.created_by_user_id,
                created_at=revision.created_at,
            )
            for revision in revisions
        ]
    )


async def op_documents_revision_create(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentRevisionItem:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    revision = await container.document_revision_repository.create(
        file_id=payload.file_id,
        revision_file_id=row.file_id,
        created_by_user_id=scope.user_id,
    )
    await record_document_event(
        container,
        file_id=payload.file_id,
        company_id=scope.company_id,
        event_type="revision_created",
        user_id=scope.user_id,
        payload={"revision_id": revision.revision_id},
    )
    return OfficeDocumentRevisionItem(
        revision_id=revision.revision_id,
        revision_number=revision.revision_number,
        file_id=revision.file_id,
        created_by_user_id=revision.created_by_user_id,
        created_at=revision.created_at,
    )


async def op_documents_events_list(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> ListResponse[OfficeDocumentEventItem]:
    _ = user
    scope = await _namespace_scope(container)
    row = await container.document_binding_repository.get(
        payload.file_id,
        scope.company_id,
        scope.namespace,
    )
    if row is None:
        raise WsCommandError("not_found", "Привязка не найдена")
    await _require_binding_catalog_access(container, row, scope.user_id)
    events = await container.document_event_repository.list_for_file(payload.file_id)
    return ListResponse[OfficeDocumentEventItem](
        items=[
            OfficeDocumentEventItem(
                event_id=event.event_id,
                event_type=event.event_type,
                user_id=event.user_id,
                created_at=event.created_at,
            )
            for event in events
        ]
    )


async def op_documents_metadata(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentMetadataResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    return OfficeDocumentMetadataResponse(file_id=row.file_id)


async def op_documents_ai_summary(
    payload: OfficeFileIdPayload,
    *,
    user: User,
    container: OfficeContainer,
) -> OfficeDocumentAiSummaryResponse:
    _ = user
    scope = await _namespace_scope(container)
    row = await _load_binding(container, scope, payload.file_id)
    await _require_binding_catalog_access(container, row, scope.user_id)
    return OfficeDocumentAiSummaryResponse(
        file_id=row.file_id,
        summary="",
        enabled=False,
    )
