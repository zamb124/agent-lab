"""
BFF: привязки документов OnlyOffice, выдача JWT редактора, скачивание для DS, callback.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from httpx import HTTPError, HTTPStatusError
from sqlalchemy.exc import IntegrityError

from apps.office.api.viewer_routes import router as office_viewer_router
from apps.office.config import OfficeSettings, get_office_settings
from apps.office.container import OfficeContainer
from apps.office.db.models import OfficeDocumentBinding
from apps.office.dependencies import ContainerDep
from apps.office.models.api import (
    OfficeCatalogCreateRequest,
    OfficeCatalogDetailResponse,
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
    OfficeDocumentEventListResponse,
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
    OfficeDocumentRevisionListResponse,
    OfficeDocumentSearchResponse,
    OfficeDocumentShareCreateRequest,
    OfficeDocumentShareItem,
    OfficeDocumentShareListResponse,
    OfficeDocumentShareResolveResponse,
    OfficeDocumentSyncRequest,
    OfficeEditorConfigResponse,
    OfficeEmptyCreateRequest,
    OfficeFileEditorSyncResponse,
    OfficeIntegrationStatusResponse,
    OfficeNamespaceCreateRequest,
    OfficeNamespaceCreateResponse,
    OfficeNamespaceItem,
    OfficeNamespaceTemplateItem,
    OfficePublicCatalogItemsResponse,
    OfficePublicResolveResponse,
    OfficeResourceAccessPatchRequest,
    OfficeResourceAccessResponse,
    OfficeResourceAccessRotateLinkResponse,
    OfficeSpreadsheetUpdateCellsRequest,
    OnlyOfficeCallbackResponse,
)
from apps.office.services.callback_dedupe import try_claim_onlyoffice_callback
from apps.office.services.callback_token import (
    decode_callback_context_token,
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
from apps.office.services.document_type import supports_onlyoffice_viewer
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from apps.office.services.minimal_ooxml import minimal_pptx_bytes, minimal_xlsx_bytes
from apps.office.services.office_access_service import PublicLinkTarget
from apps.office.services.onlyoffice_jwt import (
    decode_callback_authorization,
    decode_download_token,
)
from apps.office.services.viewer_service import file_viewer_binding_id, integration_configured
from core.clients.onlyoffice import OnlyOfficeJwtError, sign_onlyoffice_jwt_hs256
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import Context, clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.documents.placement import DocsBindResult, DocsPlacement
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.s3_client import S3ClientFactory
from core.files.types import FileCategory
from core.http import get_httpx_client
from core.logging import get_log_context, get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.pagination import OffsetPage
from core.types import JsonObject, parse_json_object, require_json_array, require_json_object
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)
router = APIRouter(tags=["office-bff"])
router.include_router(office_viewer_router)

_EMPTY_DOCX = Path(__file__).resolve().parent.parent / "templates" / "empty.docx"

_CRM_API_V1_PREFIX = "/crm/api/v1"

_DocumentBytesMutation = Callable[[bytes, str], bytes | tuple[bytes, int]]


@dataclass(frozen=True)
class _AuthenticatedOfficeContext:
    raw: Context
    active_company: Company
    user: User
    active_namespace: str | None
    language: Language | None


def _require_office_context() -> _AuthenticatedOfficeContext:
    ctx = get_context()
    if ctx is None:
        raise HTTPException(status_code=403, detail="Контекст запроса не установлен")
    if ctx.active_company is None:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    return _AuthenticatedOfficeContext(
        raw=ctx,
        active_company=ctx.active_company,
        user=ctx.user,
        active_namespace=ctx.active_namespace,
        language=ctx.language,
    )


def _http_exception_from_service_client(service: str, exc: ServiceClientError) -> HTTPException:
    msg = str(exc)
    match = re.match(r"HTTP (\d{3})", msg)
    if match:
        code = int(match.group(1))
        if 400 <= code < 600:
            return HTTPException(status_code=code, detail=msg)
    return HTTPException(
        status_code=502,
        detail=f"Сервис {service} недоступен или вернул ошибку: {msg}",
    )


async def _index_binding_if_catalog_enabled(
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


async def _index_binding_if_catalog_enabled_with_job_context(
    container: OfficeContainer,
    binding: OfficeDocumentBinding,
    *,
    company_id: str,
    workspace_namespace: str,
    user_id: str,
) -> None:
    """
    OnlyOffice callback анонимный: RagClient берёт Authorization из Context.
    Перед index-file поднимаем job context с JWT автора документа.
    """
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
        else f"office-callback:{binding.binding_id}"
    )
    session_id = f"office-callback:{binding.binding_id}"
    previous_context = get_context()
    job_context = build_job_context(
        company=company,
        user=user,
        host="office_onlyoffice_callback",
        trace_id=trace_id,
        session_id=session_id,
        channel="office",
    ).model_copy(update={"active_namespace": normalized_namespace})
    set_context(job_context)
    try:
        await _index_binding_if_catalog_enabled(
            container,
            binding,
            scope_company_id=normalized_company_id,
            scope_workspace_namespace=normalized_namespace,
            scope_user_id=normalized_user_id,
        )
    finally:
        if previous_context is not None:
            set_context(previous_context)
        else:
            clear_context()


async def _unindex_binding_from_catalog(
    container: OfficeContainer,
    catalog_id: str,
    file_id: str,
) -> None:
    await container.catalog_rag_index_service.unindex_binding(catalog_id, file_id)


def _http_exception_from_catalog_rag_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if message == "Каталог не найден":
        return HTTPException(status_code=404, detail=message)
    if message == "RAG-индекс для каталога не включён":
        return HTTPException(status_code=409, detail=message)
    if message == "Нет проиндексированных каталогов для поиска":
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=400, detail=message)


async def _resolve_catalog_for_create(
    c: OfficeContainer,
    *,
    company_id: str,
    namespace: str,
    user_id: str,
    catalog_id: str | None,
) -> str:
    cat_repo = c.catalog_repository
    if catalog_id is not None and catalog_id.strip() != "":
        cid = catalog_id.strip()
        allowed = await cat_repo.user_can_access_catalog(cid, company_id, namespace, user_id)
        if not allowed:
            raise HTTPException(status_code=403, detail="Нет доступа к каталогу")
        return cid
    accessible = await cat_repo.list_accessible_with_file_counts(
        company_id=company_id,
        namespace=namespace,
        user_id=user_id,
    )
    if len(accessible) == 1:
        return accessible[0][0].catalog_id
    if len(accessible) == 0:
        row = await cat_repo.get_or_create_default(
            company_id=company_id,
            namespace=namespace,
            owner_user_id=user_id,
        )
        return row.catalog_id
    raise HTTPException(
        status_code=400,
        detail="Укажите catalog_id: доступно несколько каталогов",
    )


async def _require_binding_catalog_access(
    c: OfficeContainer,
    row: OfficeDocumentBinding,
    user_id: str,
) -> None:
    allowed = await c.office_access_service.user_can_view_binding(
        row,
        company_id=row.company_id,
        namespace=row.namespace,
        user_id=user_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к каталогу документа")


async def _require_trashed_binding_access(
    c: OfficeContainer,
    row: OfficeDocumentBinding,
    user_id: str,
) -> None:
    allowed = await c.office_access_service.user_can_manage_trashed_binding(
        row,
        company_id=row.company_id,
        namespace=row.namespace,
        user_id=user_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к каталогу документа")


async def _user_display(c: OfficeContainer, user_id: str) -> tuple[str, str | None]:
    u = await c.user_repository.get(user_id)
    if u is not None:
        return u.name or user_id, u.avatar_url
    return user_id, None


def _safe_filename_stem(title: str) -> str:
    s = title.strip()
    s = re.sub(r"[^\w\-. ]+", "_", s, flags=re.UNICODE)
    s = s.strip("._ ")[:200]
    if not s:
        return "document"
    return s


def _office_inline_content_disposition(original_name: str) -> str:
    name = (original_name or "document").replace("\r", "").replace("\n", "")[:800]
    ascii_fallback = name.encode("ascii", "ignore").decode("ascii").strip() or "document"
    ascii_fallback = ascii_fallback.replace("\\", "_").replace('"', "'")[:200]
    encoded = quote(name, safe="")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _editor_embed_url(binding_id: str, namespace: str) -> str:
    return (
        f"/documents/embed/edit/{quote(binding_id, safe='')}?namespace={quote(namespace, safe='')}"
    )


def _onlyoffice_document_key(binding_id: str, checksum: str | None) -> str:
    """
    ONLYOFFICE `document.key` is a cache/version key, not our document identity.
    Keep identity in `binding_id`, and derive the editor key from current file bytes
    so Document Server reloads the real S3 object after every saved change.
    """
    safe_checksum = re.sub(r"[^a-zA-Z0-9_-]", "", checksum or "")[:24]
    if not safe_checksum:
        return binding_id
    return f"{binding_id}_{safe_checksum}"


def _onlyoffice_request_payload(token_payload: JsonObject, body: JsonObject) -> JsonObject:
    """
    ONLYOFFICE can sign callback/command parameters directly or wrap them in {"payload": {...}}.
    Header JWT uses the wrapper in current docs; body JWT often signs the parameters directly.
    """
    wrapped = token_payload.get("payload")
    if wrapped is not None:
        return require_json_object(wrapped, "OnlyOffice callback payload")
    if "status" in token_payload or "url" in token_payload or "key" in token_payload:
        return token_payload
    if "status" in body or "url" in body or "key" in body:
        return body
    return token_payload


def _document_mutation_lock_key(binding_id: str) -> str:
    return f"office:document:{binding_id}:mutation"


def _document_mutation_lock_release_channel(binding_id: str) -> str:
    return f"office:document:{binding_id}:mutation:released"


@asynccontextmanager
async def _document_mutation_lock(
    container: OfficeContainer,
    binding_id: str,
    *,
    wait_timeout_seconds: float = 45.0,
):
    """
    Distributed mutation lock на binding через Redis SET NX EX.

    Ожидание освобождения — pub/sub: при release lock публикуется в канал
    ``office:document:<binding_id>:mutation:released``. Это убирает busy-loop
    с ``asyncio.sleep(0.25)`` (по 4 TCP-roundtrip в секунду на каждый запрос
    в очереди). Fallback poll каждые ``_LOCK_FALLBACK_POLL_SECONDS`` сохранён
    на случай, если release произошёл до подписки или сообщение было потеряно.
    """
    client = container.redis_client
    lock_key = _document_mutation_lock_key(binding_id)
    release_channel = _document_mutation_lock_release_channel(binding_id)
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
                    raise HTTPException(status_code=409, detail="Документ уже изменяется")
                _ = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=min(remaining, _LOCK_FALLBACK_POLL_SECONDS),
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


_LOCK_FALLBACK_POLL_SECONDS = 2.0


_ONLYOFFICE_COMMAND_ERROR_DETAILS = {
    1: "document key is missing or no open document with this key was found",
    2: "callback URL is not correct or is not reachable from Document Server",
    3: "internal Document Server error",
    4: "no changes were applied before forcesave",
    5: "command is not correct",
    6: "invalid Document Server JWT token",
}

_LOCAL_DOCUMENT_SERVER_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _document_server_command_base_url(settings: OfficeSettings) -> str:
    dev_upstream = (settings.server.document_server_dev_upstream_url or "").strip().rstrip("/")
    if settings.server.env in ("development", "test") and dev_upstream:
        return dev_upstream
    return settings.office.document_server_public_url.strip().rstrip("/")


async def _post_onlyoffice_command(
    *,
    payload: JsonObject,
    binding_id: str,
    command_name: str,
    timeout: float = 10.0,
) -> int | None:
    settings = get_office_settings()
    integ = settings.office
    ds = _document_server_command_base_url(settings)
    if not ds:
        return None
    body: JsonObject = {"token": sign_onlyoffice_jwt_hs256(payload, integ.jwt_secret)}
    key = str(payload.get("key") or "").strip()
    url = f"{ds}/command"
    if key:
        url = f"{url}?shardkey={quote(key, safe='')}"
    try:
        async with get_httpx_client(timeout=timeout) as client:
            response = await client.post(url, json=body)
            _ = response.raise_for_status()
    except HTTPStatusError as exc:
        status_code = exc.response.status_code
        response_preview = exc.response.text[:500]
        logger.exception(
            "OnlyOffice command failed before mutation binding_id=%s command=%s http_status=%s response=%s",
            binding_id,
            command_name,
            status_code,
            response_preview,
        )
        raise HTTPException(
            status_code=409,
            detail=f"OnlyOffice {command_name} command failed",
        ) from exc
    except HTTPError as exc:
        logger.exception(
            "OnlyOffice command failed before mutation binding_id=%s command=%s http_status=%s response=%s",
            binding_id,
            command_name,
            None,
            "",
        )
        raise HTTPException(
            status_code=409,
            detail=f"OnlyOffice {command_name} command failed",
        ) from exc
    data = parse_json_object(response.content, "OnlyOffice command response")
    if "error" not in data:
        raise HTTPException(
            status_code=409, detail=f"OnlyOffice {command_name} returned invalid response"
        )
    error_code = data["error"]
    if not isinstance(error_code, str | int):
        raise HTTPException(
            status_code=409, detail=f"OnlyOffice {command_name} returned invalid response"
        )
    try:
        code = int(error_code)
    except ValueError:
        raise HTTPException(
            status_code=409, detail=f"OnlyOffice {command_name} returned invalid response"
        ) from None
    if code != 0:
        logger.warning(
            "OnlyOffice command returned error binding_id=%s command=%s code=%s detail=%s",
            binding_id,
            command_name,
            code,
            _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error"),
        )
    else:
        logger.info(
            "OnlyOffice command accepted binding_id=%s command=%s key=%s",
            binding_id,
            command_name,
            key,
        )
    return code


async def _force_save_open_editor_if_needed(
    *,
    binding_id: str,
    document_key: str,
) -> int | None:
    code = await _post_onlyoffice_command(
        payload={
            "c": "forcesave",
            "key": document_key,
            "userdata": f"sync:{binding_id}:{uuid.uuid4().hex}",
        },
        binding_id=binding_id,
        command_name="forcesave",
    )
    if code is None or code in (0, 1, 4):
        return code
    detail = _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error")
    raise HTTPException(
        status_code=409, detail=f"OnlyOffice forcesave failed: error={code} ({detail})"
    )


async def _drop_open_editor_sessions(
    *,
    binding_id: str,
    document_key: str,
) -> None:
    code = await _post_onlyoffice_command(
        payload={"c": "drop", "key": document_key},
        binding_id=binding_id,
        command_name="drop",
    )
    if code is None or code in (0, 1):
        return
    detail = _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error")
    raise HTTPException(status_code=409, detail=f"OnlyOffice drop failed: error={code} ({detail})")


async def _wait_for_file_change_after_forcesave(
    *,
    container: OfficeContainer,
    binding_id: str,
    file_id: str,
    previous_checksum: str | None,
    previous_file_size: int | None,
) -> None:
    for _ in range(90):
        await asyncio.sleep(0.5)
        meta = await container.files_service.get_optional(file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")
        if meta.checksum != previous_checksum or meta.file_size != previous_file_size:
            logger.info(
                "OnlyOffice forcesave materialized binding_id=%s file_id=%s old_size=%s new_size=%s",
                binding_id,
                file_id,
                previous_file_size,
                meta.file_size,
            )
            return
    logger.warning(
        "OnlyOffice forcesave callback did not update file binding_id=%s file_id=%s old_size=%s old_checksum=%s",
        binding_id,
        file_id,
        previous_file_size,
        previous_checksum,
    )
    raise HTTPException(
        status_code=409, detail="Не удалось дождаться сохранения открытого редактора"
    )


async def _require_explicit_namespace(container: OfficeContainer) -> str:
    """
    Жёсткая привязка documents к namespace.

    Каталоги и документы Office живут строго внутри одного workspace, и
    BFF не допускает «все пространства» / неявный fallback. Возвращает имя
    проверенного namespace, чтобы вызывающий мог использовать его явно.

    Системный `default` всегда валиден и при необходимости создаётся через
    `namespace_repository.list()` (тот же механизм, что и в публичном
    `GET /documents/api/v1/namespaces`).
    """
    ctx = _require_office_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    raw = (ctx.active_namespace or "").strip()
    if not raw:
        raise HTTPException(
            status_code=400,
            detail="Не выбрано пространство (X-Platform-Namespace) для документов",
        )
    if raw == "default":
        _ = await container.namespace_repository.list(limit=1)
    found = await container.namespace_repository.get(raw)
    if found is None:
        raise HTTPException(
            status_code=400,
            detail=f"Пространство «{raw}» не найдено в активной компании",
        )
    if found.company_id != ctx.active_company.company_id:
        raise HTTPException(
            status_code=403,
            detail="Пространство не принадлежит активной компании",
        )
    return found.name


@router.get("/integration/status", response_model=OfficeIntegrationStatusResponse)
async def integration_status() -> OfficeIntegrationStatusResponse:
    ok, detail = integration_configured()
    return OfficeIntegrationStatusResponse(configured=ok, detail=detail)


@router.get("/files/{file_id}/editor-config", response_model=OfficeEditorConfigResponse)
async def file_editor_config(
    file_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    ctx = _require_office_context()
    meta = await container.files_service.get_optional(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != ctx.active_company.company_id:
        raise HTTPException(status_code=403, detail="Файл не принадлежит компании")
    file_category, onlyoffice_document_type = resolve_binding_metadata(
        meta.original_name,
        (meta.content_type or "application/octet-stream").split(";")[0].strip(),
    )
    user_name = ctx.user.name or ctx.user.email or ctx.user.user_id
    editor_lang = container.viewer_service.default_editor_lang(ctx.language)
    return await container.viewer_service.open_config_for_file(
        request=request,
        file_record=meta,
        company_id=ctx.active_company.company_id,
        user_id=ctx.user.user_id,
        user_name=user_name,
        editor_lang=editor_lang,
        file_category=file_category,
        onlyoffice_document_type=onlyoffice_document_type,
    )


@router.post("/files/{file_id}/sync", response_model=OfficeFileEditorSyncResponse)
async def sync_file_editor_state(
    file_id: str,
    container: ContainerDep,
    body: OfficeDocumentSyncRequest | None = None,
) -> OfficeFileEditorSyncResponse:
    ctx = _require_office_context()
    sync_options = body or OfficeDocumentSyncRequest()
    binding_id = file_viewer_binding_id(file_id)
    async with _document_mutation_lock(container, binding_id):
        meta = await container.files_service.get_optional(file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")
        if meta.company_id != ctx.active_company.company_id:
            raise HTTPException(status_code=403, detail="Файл не принадлежит компании")
        if not supports_onlyoffice_viewer(
            meta.original_name,
            (meta.content_type or "application/octet-stream").split(";")[0].strip(),
        ):
            return OfficeFileEditorSyncResponse(
                file_id=meta.file_id,
                checksum=meta.checksum,
                file_size=meta.file_size,
            )
        document_key = _onlyoffice_document_key(binding_id, meta.checksum)
        if sync_options.settle_ms > 0:
            await asyncio.sleep(sync_options.settle_ms / 1000)
        force_code = await _force_save_open_editor_if_needed(
            binding_id=binding_id,
            document_key=document_key,
        )
        if sync_options.close and force_code == 4:
            await asyncio.sleep(1.5)
            force_code = await _force_save_open_editor_if_needed(
                binding_id=binding_id,
                document_key=document_key,
            )
        logger.info(
            "OnlyOffice file sync command result binding_id=%s file_id=%s close=%s dirty=%s force_code=%s",
            binding_id,
            meta.file_id,
            sync_options.close,
            sync_options.dirty,
            force_code,
        )
        if sync_options.close and sync_options.dirty is True and force_code in (1, 4):
            detail = _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(force_code, "unknown error")
            raise HTTPException(
                status_code=409,
                detail=f"OnlyOffice did not accept pending editor changes yet: error={force_code} ({detail})",
            )
        if force_code == 0:
            await _wait_for_file_change_after_forcesave(
                container=container,
                binding_id=binding_id,
                file_id=meta.file_id,
                previous_checksum=meta.checksum,
                previous_file_size=meta.file_size,
            )
            meta = await container.files_service.get_optional(file_id)
            if meta is None:
                raise HTTPException(status_code=404, detail="Файл не найден")
        if sync_options.close and force_code in (0, 4):
            await _drop_open_editor_sessions(
                binding_id=binding_id,
                document_key=document_key,
            )
    return OfficeFileEditorSyncResponse(
        file_id=meta.file_id,
        checksum=meta.checksum,
        file_size=meta.file_size,
    )


@router.get("/namespaces", response_model=OffsetPage[OfficeNamespaceItem])
async def list_namespaces(container: ContainerDep) -> OffsetPage[OfficeNamespaceItem]:
    ctx = _require_office_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    rows = await container.namespace_repository.list(limit=1000)
    items: list[OfficeNamespaceItem] = [
        OfficeNamespaceItem(name=ns.name.strip(), is_default=bool(ns.is_default))
        for ns in rows
        if ns.name and ns.name.strip()
    ]
    return OffsetPage[OfficeNamespaceItem](
        items=items, total=len(items), limit=len(items), offset=0
    )


@router.get("/namespaces/templates", response_model=OffsetPage[OfficeNamespaceTemplateItem])
async def list_namespace_templates_proxy(
    container: ContainerDep,
) -> OffsetPage[OfficeNamespaceTemplateItem]:
    ctx = _require_office_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    path = f"{_CRM_API_V1_PREFIX}/namespaces/templates"
    try:
        raw = await container.service_client.get("crm", path)
    except ServiceClientError as e:
        raise _http_exception_from_service_client("crm", e) from e
    raw_items_value = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(raw_items_value, list):
        raise HTTPException(
            status_code=502, detail="CRM: неверный формат списка шаблонов namespace"
        )
    raw_items = require_json_array(raw_items_value, "crm.namespace_templates.items")
    out: list[OfficeNamespaceTemplateItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise HTTPException(status_code=502, detail="CRM: элемент шаблона namespace не объект")
        tid = item.get("template_id")
        if not isinstance(tid, str) or not tid.strip():
            raise HTTPException(status_code=502, detail="CRM: у шаблона нет template_id")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(status_code=502, detail="CRM: у шаблона нет name")
        desc = item.get("description")
        icon = item.get("icon")
        is_system = bool(item.get("is_system"))
        et = item.get("entity_type_ids")
        entity_type_ids: list[str] = []
        if isinstance(et, list):
            entity_type_ids = [str(x) for x in et if isinstance(x, str) and x.strip()]
        out.append(
            OfficeNamespaceTemplateItem(
                template_id=tid.strip(),
                name=name.strip(),
                description=desc.strip() if isinstance(desc, str) and desc.strip() else None,
                icon=icon.strip() if isinstance(icon, str) and icon.strip() else None,
                is_system=is_system,
                entity_type_ids=entity_type_ids,
            )
        )
    return OffsetPage[OfficeNamespaceTemplateItem](
        items=out, total=len(out), limit=len(out), offset=0
    )


@router.post("/namespaces", response_model=OfficeNamespaceCreateResponse, status_code=201)
async def create_namespace_proxy(
    body: OfficeNamespaceCreateRequest,
    container: ContainerDep,
) -> OfficeNamespaceCreateResponse:
    ctx = _require_office_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    path = f"{_CRM_API_V1_PREFIX}/namespaces"
    payload = {
        "name": body.name.strip(),
        "description": body.description.strip() if body.description else None,
        "template_id": body.template_id.strip(),
    }
    try:
        raw = await container.service_client.post("crm", path, json=payload)
    except ServiceClientError as e:
        raise _http_exception_from_service_client("crm", e) from e
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="CRM: неверный ответ при создании namespace")
    name = raw.get("name")
    company_id = raw.get("company_id")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=502, detail="CRM: в ответе нет name")
    if not isinstance(company_id, str) or not company_id.strip():
        raise HTTPException(status_code=502, detail="CRM: в ответе нет company_id")
    desc = raw.get("description")
    return OfficeNamespaceCreateResponse(
        name=name.strip(),
        company_id=company_id.strip(),
        description=desc.strip() if isinstance(desc, str) and desc.strip() else None,
        is_default=bool(raw.get("is_default")),
    )


@router.get("/company-members")
async def list_company_members_for_catalogs(
    container: ContainerDep,
) -> list[JsonObject]:
    ctx = _require_office_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    company = await container.company_repository.get(ctx.active_company.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    out: list[JsonObject] = []
    for member_user_id, roles in company.members.items():
        u = await container.user_repository.get(member_user_id)
        if u is None:
            continue
        member_email = u.emails[0] if u.emails else None
        roles_list = roles
        joined_at = u.created_at.isoformat() if u.created_at else None
        out.append(
            {
                "user_id": member_user_id,
                "name": u.name,
                "email": member_email,
                "roles": roles_list,
                "joined_at": joined_at,
                "avatar_url": u.avatar_url,
            }
        )
    return out


@router.get("/catalogs", response_model=OfficeCatalogListResponse)
async def list_catalogs(container: ContainerDep) -> OfficeCatalogListResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    rows = await container.catalog_repository.list_accessible_with_file_counts(
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        user_id=ctx.user.user_id,
    )
    out: list[OfficeCatalogListItem] = []
    for cat, file_count in rows:
        display_name, avatar_url = await _user_display(container, cat.owner_user_id)
        out.append(
            OfficeCatalogListItem(
                catalog_id=cat.catalog_id,
                parent_catalog_id=cat.parent_catalog_id,
                title=cat.title,
                file_count=file_count,
                owner_user_id=cat.owner_user_id,
                owner_display_name=display_name,
                owner_avatar_url=avatar_url,
                is_owner=cat.owner_user_id == ctx.user.user_id,
                is_public=cat.is_public,
                rag_index_enabled=cat.rag_index_enabled,
                rag_index_include_subcatalogs=cat.rag_index_include_subcatalogs,
            )
        )
    return OfficeCatalogListResponse(items=out)


@router.post("/catalogs", response_model=OfficeCatalogDetailResponse)
async def create_catalog(
    body: OfficeCatalogCreateRequest,
    container: ContainerDep,
) -> OfficeCatalogDetailResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    if body.parent_catalog_id is not None:
        parent_allowed = await container.catalog_repository.user_can_access_catalog(
            body.parent_catalog_id,
            ctx.active_company.company_id,
            namespace,
            ctx.user.user_id,
        )
        if not parent_allowed:
            raise HTTPException(status_code=403, detail="Нет доступа к родительскому каталогу")
        is_parent_owner = await container.catalog_repository.user_is_owner(
            body.parent_catalog_id,
            ctx.active_company.company_id,
            namespace,
            ctx.user.user_id,
        )
        if not is_parent_owner:
            raise HTTPException(
                status_code=403,
                detail="Подкаталог может создать только владелец родительского каталога",
            )
    try:
        cat = await container.catalog_repository.create(
            company_id=ctx.active_company.company_id,
            namespace=namespace,
            title=body.title,
            owner_user_id=ctx.user.user_id,
            is_public=body.is_public,
            parent_catalog_id=body.parent_catalog_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    display_name, avatar_url = await _user_display(container, cat.owner_user_id)
    return OfficeCatalogDetailResponse(
        catalog_id=cat.catalog_id,
        parent_catalog_id=cat.parent_catalog_id,
        title=cat.title,
        owner_user_id=cat.owner_user_id,
        owner_display_name=display_name,
        owner_avatar_url=avatar_url,
        is_owner=True,
        is_public=cat.is_public,
    )


@router.get("/catalogs/{catalog_id}", response_model=OfficeCatalogDetailResponse)
async def get_catalog(
    catalog_id: str,
    container: ContainerDep,
) -> OfficeCatalogDetailResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    allowed = await container.catalog_repository.user_can_access_catalog(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    cat = await container.catalog_repository.get(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
    )
    if cat is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    display_name, avatar_url = await _user_display(container, cat.owner_user_id)
    return OfficeCatalogDetailResponse(
        catalog_id=cat.catalog_id,
        parent_catalog_id=cat.parent_catalog_id,
        title=cat.title,
        owner_user_id=cat.owner_user_id,
        owner_display_name=display_name,
        owner_avatar_url=avatar_url,
        is_owner=cat.owner_user_id == ctx.user.user_id,
        is_public=cat.is_public,
    )


@router.patch("/catalogs/{catalog_id}", response_model=OfficeCatalogDetailResponse)
async def patch_catalog(
    catalog_id: str,
    body: OfficeCatalogPatchRequest,
    container: ContainerDep,
) -> OfficeCatalogDetailResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(
            status_code=403,
            detail="Только владелец может изменять каталог",
        )
    updated = await container.catalog_repository.update_catalog(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        title=body.title,
        is_public=body.is_public,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    display_name, avatar_url = await _user_display(container, updated.owner_user_id)
    return OfficeCatalogDetailResponse(
        catalog_id=updated.catalog_id,
        parent_catalog_id=updated.parent_catalog_id,
        title=updated.title,
        owner_user_id=updated.owner_user_id,
        owner_display_name=display_name,
        owner_avatar_url=avatar_url,
        is_owner=True,
        is_public=updated.is_public,
    )


@router.delete("/catalogs/{catalog_id}", status_code=204)
async def delete_catalog_endpoint(
    catalog_id: str,
    container: ContainerDep,
) -> Response:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может удалить каталог")
    catalog = await container.catalog_repository.get(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
    )
    if catalog is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    if catalog.rag_index_enabled:
        try:
            await container.catalog_rag_index_service.disable(catalog_id)
        except ServiceClientError as exc:
            raise _http_exception_from_service_client("rag", exc) from exc
        except ValueError as exc:
            raise _http_exception_from_catalog_rag_value_error(exc) from exc
    try:
        ok = await container.catalog_repository.delete_catalog(
            catalog_id,
            ctx.active_company.company_id,
            namespace,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    return Response(status_code=204)


@router.post(
    "/catalogs/{catalog_id}/rag-index/enable",
    response_model=OfficeCatalogRagIndexEnableResponse,
)
async def enable_catalog_rag_index(
    catalog_id: str,
    container: ContainerDep,
) -> OfficeCatalogRagIndexEnableResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(
            status_code=403, detail="Только владелец может управлять RAG-индексом каталога"
        )
    try:
        return await container.catalog_rag_index_service.enable(catalog_id)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc


@router.post(
    "/catalogs/{catalog_id}/rag-index/disable",
    response_model=OfficeCatalogRagIndexDisableResponse,
)
async def disable_catalog_rag_index(
    catalog_id: str,
    container: ContainerDep,
) -> OfficeCatalogRagIndexDisableResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(
            status_code=403, detail="Только владелец может управлять RAG-индексом каталога"
        )
    try:
        await container.catalog_rag_index_service.disable(catalog_id)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    return OfficeCatalogRagIndexDisableResponse()


@router.post(
    "/catalogs/{catalog_id}/rag-index/rebuild",
    status_code=202,
    response_model=OfficeCatalogRagIndexRebuildResponse,
)
async def rebuild_catalog_rag_index(
    catalog_id: str,
    container: ContainerDep,
) -> OfficeCatalogRagIndexRebuildResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(
            status_code=403, detail="Только владелец может управлять RAG-индексом каталога"
        )
    try:
        return await container.catalog_rag_index_service.rebuild_catalog(catalog_id)
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc


@router.get(
    "/catalogs/{catalog_id}/rag-index/status",
    response_model=OfficeCatalogRagIndexStatusResponse,
)
async def catalog_rag_index_status(
    catalog_id: str,
    container: ContainerDep,
) -> OfficeCatalogRagIndexStatusResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    allowed = await container.catalog_repository.user_can_access_catalog(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к каталогу")
    try:
        return await container.catalog_rag_index_service.get_status(catalog_id)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc


@router.patch(
    "/catalogs/{catalog_id}/rag-index/settings",
    response_model=OfficeCatalogRagIndexSettingsResponse,
)
async def patch_catalog_rag_index_settings(
    catalog_id: str,
    body: OfficeCatalogRagIndexSettingsPatchRequest,
    container: ContainerDep,
) -> OfficeCatalogRagIndexSettingsResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(
            status_code=403, detail="Только владелец может управлять RAG-индексом каталога"
        )
    try:
        return await container.catalog_rag_index_service.set_include_subcatalogs(
            catalog_id,
            include_subcatalogs=body.include_subcatalogs,
        )
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc


@router.post(
    "/catalogs/{catalog_id}/rag-index/search",
    response_model=OfficeCatalogSemanticSearchResponse,
)
async def search_catalog_rag_index(
    catalog_id: str,
    body: OfficeCatalogSemanticSearchRequest,
    container: ContainerDep,
) -> OfficeCatalogSemanticSearchResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    allowed = await container.catalog_repository.user_can_access_catalog(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к каталогу")
    try:
        return await container.catalog_rag_index_service.search_catalog(
            catalog_id,
            body.query,
            limit=body.limit,
        )
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc


@router.get("/catalogs/{catalog_id}/members", response_model=OfficeCatalogMembersResponse)
async def list_catalog_members(
    catalog_id: str,
    container: ContainerDep,
) -> OfficeCatalogMembersResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    allowed = await container.catalog_repository.user_can_access_catalog(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    cat = await container.catalog_repository.get(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
    )
    if cat is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    member_rows = await container.catalog_repository.list_members(catalog_id)
    member_ids = {m.user_id for m in member_rows}
    member_ids.add(cat.owner_user_id)
    items: list[OfficeCatalogMemberItem] = []
    for uid in sorted(member_ids):
        display_name, avatar_url = await _user_display(container, uid)
        items.append(
            OfficeCatalogMemberItem(
                user_id=uid,
                display_name=display_name,
                avatar_url=avatar_url,
            )
        )
    return OfficeCatalogMembersResponse(members=items)


@router.post("/catalogs/{catalog_id}/members", response_model=OfficeCatalogMembersResponse)
async def add_catalog_member(
    catalog_id: str,
    body: OfficeCatalogMemberAddRequest,
    container: ContainerDep,
) -> OfficeCatalogMembersResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может добавлять участников")
    try:
        _ = await container.catalog_repository.add_member(
            catalog_id,
            body.user_id.strip(),
            company_id=ctx.active_company.company_id,
            namespace=namespace,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await list_catalog_members(catalog_id, container)


@router.delete("/catalogs/{catalog_id}/members/{member_user_id}", status_code=204)
async def remove_catalog_member(
    catalog_id: str,
    member_user_id: str,
    container: ContainerDep,
) -> Response:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может удалять участников")
    cat = await container.catalog_repository.get(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
    )
    if cat is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    if member_user_id == cat.owner_user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить владельца каталога")
    ok = await container.catalog_repository.remove_member(catalog_id, member_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Участник не найден")
    return Response(status_code=204)


@router.get("/catalogs/{catalog_id}/access", response_model=OfficeResourceAccessResponse)
async def get_catalog_access(
    catalog_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeResourceAccessResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может управлять доступом")
    try:
        return await container.office_access_service.get_catalog_access(
            catalog_id,
            ctx.active_company.company_id,
            namespace,
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/catalogs/{catalog_id}/access", response_model=OfficeResourceAccessResponse)
async def patch_catalog_access(
    catalog_id: str,
    body: OfficeResourceAccessPatchRequest,
    container: ContainerDep,
    request: Request,
) -> OfficeResourceAccessResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может управлять доступом")
    try:
        response, _raw_token = await container.office_access_service.patch_catalog_access(
            catalog_id,
            ctx.active_company.company_id,
            namespace,
            body,
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return response


@router.post(
    "/catalogs/{catalog_id}/access/link/rotate",
    response_model=OfficeResourceAccessRotateLinkResponse,
)
async def rotate_catalog_access_link(
    catalog_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeResourceAccessRotateLinkResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    is_owner = await container.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может управлять доступом")
    try:
        return await container.office_access_service.rotate_catalog_link(
            catalog_id,
            ctx.active_company.company_id,
            namespace,
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/documents/{binding_id}/access", response_model=OfficeResourceAccessResponse)
async def get_document_access(
    binding_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeResourceAccessResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    return await container.office_access_service.get_binding_access(row, request)


@router.patch("/documents/{binding_id}/access", response_model=OfficeResourceAccessResponse)
async def patch_document_access(
    binding_id: str,
    body: OfficeResourceAccessPatchRequest,
    container: ContainerDep,
    request: Request,
) -> OfficeResourceAccessResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    try:
        response, _raw_token = await container.office_access_service.patch_binding_access(
            row,
            body,
            request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return response


@router.post(
    "/documents/{binding_id}/access/link/rotate",
    response_model=OfficeResourceAccessRotateLinkResponse,
)
async def rotate_document_access_link(
    binding_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeResourceAccessRotateLinkResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    try:
        return await container.office_access_service.rotate_binding_link(row, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


OfficeDocumentSortKey = Literal["created_at", "title", "file_size", "updated_at"]
OfficeDocumentSortOrder = Literal["asc", "desc"]


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


@router.get("/documents", response_model=OfficeDocumentListResponse)
async def list_documents(
    container: ContainerDep,
    catalog_id: Annotated[str | None, Query(min_length=1)] = None,
    catalog_ids: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=500)] = None,
    sort: Annotated[OfficeDocumentSortKey, Query()] = "updated_at",
    order: Annotated[OfficeDocumentSortOrder, Query()] = "desc",
) -> OfficeDocumentListResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    raw: list[str] = []
    if catalog_ids:
        raw.extend(catalog_ids)
    if catalog_id is not None and catalog_id.strip() != "":
        raw.append(catalog_id.strip())
    seen: set[str] = set()
    resolved_ids: list[str] = []
    for item in raw:
        tid = (item or "").strip()
        if tid == "" or tid in seen:
            continue
        seen.add(tid)
        resolved_ids.append(tid)
    if not resolved_ids:
        raise HTTPException(
            status_code=422,
            detail="Укажите catalog_id или хотя бы одно значение catalog_ids",
        )
    for cid in resolved_ids:
        allowed = await container.catalog_repository.user_can_access_catalog(
            cid,
            ctx.active_company.company_id,
            namespace,
            ctx.user.user_id,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Нет доступа к каталогу")
    rows = await container.document_binding_repository.list_by_company_namespace_and_catalogs(
        ctx.active_company.company_id,
        namespace,
        resolved_ids,
    )
    items = await bindings_to_items(container, rows)
    if q is not None and q.strip() != "":
        needle = q.strip().casefold()
        items = [item for item in items if needle in item.title.casefold()]
    items = _sort_office_document_items(items, sort, order)
    return OfficeDocumentListResponse(items=items)


@router.post("/documents", response_model=OfficeDocumentCreateResponse)
async def upload_document(
    container: ContainerDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    catalog_id: Annotated[str | None, Form()] = None,
) -> OfficeDocumentCreateResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()

    settings = get_settings()
    if not settings.s3.enabled or not settings.s3.default_bucket:
        raise HTTPException(status_code=503, detail="S3 не настроен")

    raw_name = file.filename or "document"
    doc_title = (title or "").strip() or Path(raw_name).stem or "Документ"
    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Пустой файл")
    guessed_ct = file.content_type or "application/octet-stream"
    normalized_ct = guessed_ct.split(";", 1)[0].strip()
    file_category, onlyoffice_document_type = resolve_binding_metadata(raw_name, normalized_ct)
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(entity_id=namespace),
        retention=default_retention_for_source(FileSourceKind.OFFICE_DOCUMENT),
        post_create=FilePostCreate(is_public=False),
    )
    meta = await container.files_service.create(
        spec=spec,
        data=data,
        original_name=raw_name,
        content_type=guessed_ct.split(";")[0].strip(),
    )
    resolved_catalog_id = await _resolve_catalog_for_create(
        container,
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        user_id=ctx.user.user_id,
        catalog_id=catalog_id,
    )
    row = await container.document_binding_repository.create(
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        catalog_id=resolved_catalog_id,
        file_id=meta.file_id,
        file_category=file_category,
        onlyoffice_document_type=onlyoffice_document_type,
        title=doc_title,
        created_by_user_id=ctx.user.user_id,
    )
    try:
        await _index_binding_if_catalog_enabled(container, row)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    return OfficeDocumentCreateResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        title=row.title,
        editor_url=_editor_embed_url(row.binding_id, namespace),
    )


@router.post("/documents/bind", response_model=DocsBindResult)
async def bind_file_to_catalog(
    body: DocsPlacement,
    container: ContainerDep,
) -> DocsBindResult:
    ctx = _require_office_context()
    return await container.docs_placement_service.bind(
        body,
        company_id=ctx.active_company.company_id,
        user_id=ctx.user.user_id,
    )


@router.post("/documents/from-file", response_model=OfficeDocumentCreateResponse)
async def open_existing_file_as_document(
    body: OfficeDocumentFromFileRequest,
    container: ContainerDep,
) -> OfficeDocumentCreateResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    file_id = body.file_id.strip()
    meta = await container.files_service.get_optional(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != ctx.active_company.company_id:
        raise HTTPException(status_code=403, detail="Файл не принадлежит компании")

    file_category, onlyoffice_document_type = resolve_binding_metadata(
        meta.original_name,
        (meta.content_type or "application/octet-stream").split(";")[0].strip(),
    )

    existing = await container.document_binding_repository.get_by_file_for_company(
        file_id,
        ctx.active_company.company_id,
        namespace,
    )
    if existing is not None:
        await _require_binding_catalog_access(container, existing, ctx.user.user_id)
        return OfficeDocumentCreateResponse(
            binding_id=existing.binding_id,
            file_id=existing.file_id,
            catalog_id=existing.catalog_id,
            file_category=existing.file_category,
            onlyoffice_document_type=existing.onlyoffice_document_type,
            title=existing.title,
            editor_url=_editor_embed_url(existing.binding_id, namespace),
        )

    resolved_catalog_id = await _resolve_catalog_for_create(
        container,
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        user_id=ctx.user.user_id,
        catalog_id=body.catalog_id,
    )
    title = (body.title or "").strip() or Path(meta.original_name).stem or meta.original_name
    try:
        row = await container.document_binding_repository.create(
            company_id=ctx.active_company.company_id,
            namespace=namespace,
            catalog_id=resolved_catalog_id,
            file_id=meta.file_id,
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            title=title,
            created_by_user_id=ctx.user.user_id,
        )
    except IntegrityError:
        existing = await container.document_binding_repository.get_by_file_for_company(
            file_id,
            ctx.active_company.company_id,
            namespace,
        )
        if existing is None:
            raise
        await _require_binding_catalog_access(container, existing, ctx.user.user_id)
        return OfficeDocumentCreateResponse(
            binding_id=existing.binding_id,
            file_id=existing.file_id,
            catalog_id=existing.catalog_id,
            file_category=existing.file_category,
            onlyoffice_document_type=existing.onlyoffice_document_type,
            title=existing.title,
            editor_url=_editor_embed_url(existing.binding_id, namespace),
        )
    try:
        await _index_binding_if_catalog_enabled(container, row)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    return OfficeDocumentCreateResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        title=row.title,
        editor_url=_editor_embed_url(row.binding_id, namespace),
    )


@router.post("/documents/empty", response_model=OfficeDocumentCreateResponse)
async def create_empty_document(
    body: OfficeEmptyCreateRequest,
    container: ContainerDep,
) -> OfficeDocumentCreateResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()

    settings = get_settings()
    if not settings.s3.enabled or not settings.s3.default_bucket:
        raise HTTPException(status_code=503, detail="S3 не настроен")

    stem = _safe_filename_stem(body.title)
    kind = body.document_type
    if kind == "word":
        if not _EMPTY_DOCX.is_file():
            raise HTTPException(status_code=500, detail="Шаблон пустого документа не найден")
        data = _EMPTY_DOCX.read_bytes()
        original_name = f"{stem}.docx"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        file_category = FileCategory.OFFICE_DOC.value
        onlyoffice_document_type = "word"
    elif kind == "cell":
        fmt = body.spreadsheet_format
        if fmt == "csv":
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
        source_ref=FileSourceRef(entity_id=namespace),
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
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        user_id=ctx.user.user_id,
        catalog_id=body.catalog_id,
    )
    row = await container.document_binding_repository.create(
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        catalog_id=resolved_catalog_id,
        file_id=meta.file_id,
        file_category=file_category,
        onlyoffice_document_type=onlyoffice_document_type,
        title=body.title.strip(),
        created_by_user_id=ctx.user.user_id,
    )
    try:
        await _index_binding_if_catalog_enabled(container, row)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    return OfficeDocumentCreateResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        title=row.title,
        editor_url=_editor_embed_url(row.binding_id, namespace),
    )


@router.post(
    "/documents/{binding_id}/editor-session",
    response_model=OfficeDocumentEditorSessionResponse,
)
async def document_editor_session(
    binding_id: str,
    container: ContainerDep,
) -> OfficeDocumentEditorSessionResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    return OfficeDocumentEditorSessionResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        title=row.title,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        namespace=namespace,
        editor_url=_editor_embed_url(row.binding_id, namespace),
    )


@router.post(
    "/documents/{binding_id}/sync",
    response_model=OfficeDocumentEditorSessionResponse,
)
async def sync_document_editor_state(
    binding_id: str,
    container: ContainerDep,
    body: OfficeDocumentSyncRequest | None = None,
) -> OfficeDocumentEditorSessionResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    sync_options = body or OfficeDocumentSyncRequest()
    async with _document_mutation_lock(container, binding_id):
        row = await container.document_binding_repository.get_for_company(
            binding_id,
            ctx.active_company.company_id,
            namespace,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Привязка не найдена")
        await _require_binding_catalog_access(container, row, ctx.user.user_id)
        meta = await container.files_service.get_optional(row.file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")

        if not supports_onlyoffice_viewer(
            meta.original_name,
            (meta.content_type or "application/octet-stream").split(";")[0].strip(),
        ):
            return OfficeDocumentEditorSessionResponse(
                binding_id=row.binding_id,
                file_id=row.file_id,
                catalog_id=row.catalog_id,
                title=row.title,
                file_category=row.file_category,
                onlyoffice_document_type=row.onlyoffice_document_type,
                namespace=namespace,
                editor_url=_editor_embed_url(row.binding_id, namespace),
            )

        document_key = _onlyoffice_document_key(row.binding_id, meta.checksum)
        if sync_options.settle_ms > 0:
            await asyncio.sleep(sync_options.settle_ms / 1000)
        force_code = await _force_save_open_editor_if_needed(
            binding_id=row.binding_id,
            document_key=document_key,
        )
        if sync_options.close and force_code == 4:
            await asyncio.sleep(1.5)
            force_code = await _force_save_open_editor_if_needed(
                binding_id=row.binding_id,
                document_key=document_key,
            )
        logger.info(
            "OnlyOffice sync command result binding_id=%s file_id=%s close=%s dirty=%s force_code=%s",
            row.binding_id,
            row.file_id,
            sync_options.close,
            sync_options.dirty,
            force_code,
        )
        if sync_options.close and sync_options.dirty is True and force_code in (1, 4):
            detail = _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(force_code, "unknown error")
            raise HTTPException(
                status_code=409,
                detail=f"OnlyOffice did not accept pending editor changes yet: error={force_code} ({detail})",
            )
        if force_code == 0:
            await _wait_for_file_change_after_forcesave(
                container=container,
                binding_id=row.binding_id,
                file_id=row.file_id,
                previous_checksum=meta.checksum,
                previous_file_size=meta.file_size,
            )
        if sync_options.close and force_code in (0, 4):
            await _drop_open_editor_sessions(
                binding_id=row.binding_id,
                document_key=document_key,
            )

    return OfficeDocumentEditorSessionResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        title=row.title,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        namespace=namespace,
        editor_url=_editor_embed_url(row.binding_id, namespace),
    )


async def _apply_document_bytes_mutation(
    *,
    binding_id: str,
    container: OfficeContainer,
    mutate: _DocumentBytesMutation,
    changed_count: int | None = None,
) -> OfficeDocumentMutationResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    async with _document_mutation_lock(container, binding_id):
        row = await container.document_binding_repository.get_for_company(
            binding_id,
            ctx.active_company.company_id,
            namespace,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Привязка не найдена")
        await _require_binding_catalog_access(container, row, ctx.user.user_id)
        meta = await container.files_service.get_optional(row.file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")
        caps = container.viewer_service.capabilities_for_file(
            file_category=row.file_category,
            file_record=meta,
        )
        if not caps.server_mutations:
            raise HTTPException(
                status_code=422, detail="Серверные мутации недоступны для этого типа файла"
            )
        document_key = _onlyoffice_document_key(row.binding_id, meta.checksum)
        force_code = await _force_save_open_editor_if_needed(
            binding_id=row.binding_id,
            document_key=document_key,
        )
        if force_code == 0:
            await _wait_for_file_change_after_forcesave(
                container=container,
                binding_id=row.binding_id,
                file_id=row.file_id,
                previous_checksum=meta.checksum,
                previous_file_size=meta.file_size,
            )
            meta = await container.files_service.get_optional(row.file_id)
            if meta is None:
                raise HTTPException(status_code=404, detail="Файл не найден")
        if force_code in (0, 4):
            await _drop_open_editor_sessions(
                binding_id=row.binding_id,
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
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if isinstance(mutation_result, tuple):
            new_bytes, changed = mutation_result
        else:
            new_bytes, changed = mutation_result, changed_count
        if changed == 0:
            return OfficeDocumentMutationResponse(
                binding_id=row.binding_id,
                file_id=row.file_id,
                checksum=meta.checksum,
                file_size=meta.file_size,
                editor_url=_editor_embed_url(row.binding_id, namespace),
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
            binding_id=row.binding_id,
            file_id=row.file_id,
            checksum=digest,
            file_size=len(new_bytes),
            editor_url=_editor_embed_url(row.binding_id, namespace),
            changed_count=changed,
        )


@router.post(
    "/documents/{binding_id}/mutations/replace-text",
    response_model=OfficeDocumentMutationResponse,
)
async def replace_document_text(
    binding_id: str,
    body: OfficeDocumentReplaceTextRequest,
    container: ContainerDep,
) -> OfficeDocumentMutationResponse:
    return await _apply_document_bytes_mutation(
        binding_id=binding_id,
        container=container,
        mutate=lambda data, original_name: replace_text_in_document(
            data=data,
            original_name=original_name,
            find=body.find,
            replace=body.replace,
            match_case=body.match_case,
        ),
    )


@router.post(
    "/documents/{binding_id}/mutations/append-text",
    response_model=OfficeDocumentMutationResponse,
)
async def append_document_text(
    binding_id: str,
    body: OfficeDocumentAppendTextRequest,
    container: ContainerDep,
) -> OfficeDocumentMutationResponse:
    return await _apply_document_bytes_mutation(
        binding_id=binding_id,
        container=container,
        mutate=lambda data, original_name: append_text_to_document(
            data=data,
            original_name=original_name,
            text=body.text,
        ),
        changed_count=None,
    )


@router.post(
    "/documents/{binding_id}/mutations/update-cells",
    response_model=OfficeDocumentMutationResponse,
)
async def update_document_cells(
    binding_id: str,
    body: OfficeSpreadsheetUpdateCellsRequest,
    container: ContainerDep,
) -> OfficeDocumentMutationResponse:
    return await _apply_document_bytes_mutation(
        binding_id=binding_id,
        container=container,
        mutate=lambda data, original_name: update_spreadsheet_cells(
            data=data,
            original_name=original_name,
            sheet=body.sheet,
            cells=body.cells,
        ),
        changed_count=None,
    )


@router.patch(
    "/documents/{binding_id}",
    response_model=OfficeDocumentRenameResponse,
)
async def rename_document(
    binding_id: str,
    body: OfficeDocumentRenameRequest,
    container: ContainerDep,
) -> OfficeDocumentRenameResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    updated = await container.document_binding_repository.update_title(
        binding_id,
        ctx.active_company.company_id,
        namespace,
        body.title.strip(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    return OfficeDocumentRenameResponse(
        binding_id=updated.binding_id,
        title=updated.title,
    )


@router.delete("/documents/{binding_id}", status_code=204)
async def delete_document(binding_id: str, container: ContainerDep) -> Response:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    if row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    try:
        await _unindex_binding_from_catalog(container, row.catalog_id, row.file_id)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    ok = await container.document_binding_repository.soft_delete(
        binding_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await record_document_event(
        container,
        binding_id=binding_id,
        company_id=ctx.active_company.company_id,
        event_type="deleted",
        user_id=ctx.user.user_id,
    )
    return Response(status_code=204)


@router.get("/documents/deleted", response_model=OfficeDocumentListResponse)
async def list_deleted_documents(container: ContainerDep) -> OfficeDocumentListResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    rows = await container.document_binding_repository.list_deleted_by_namespace(
        ctx.active_company.company_id,
        namespace,
    )
    items = await bindings_to_items(container, rows)
    return OfficeDocumentListResponse(items=items)


@router.post("/documents/{binding_id}/restore", response_model=OfficeDocumentItem)
async def restore_document(binding_id: str, container: ContainerDep) -> OfficeDocumentItem:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.restore(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена в корзине")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    await record_document_event(
        container,
        binding_id=binding_id,
        company_id=ctx.active_company.company_id,
        event_type="restored",
        user_id=ctx.user.user_id,
    )
    try:
        await _index_binding_if_catalog_enabled(container, row)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    return await binding_to_item(container, row)


@router.delete("/documents/{binding_id}/permanent", status_code=204)
async def permanent_delete_document(binding_id: str, container: ContainerDep) -> Response:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена в корзине")
    await _require_trashed_binding_access(container, row, ctx.user.user_id)
    try:
        await _unindex_binding_from_catalog(container, row.catalog_id, row.file_id)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    ok = await container.document_binding_repository.delete_binding(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    _ = await container.files_service.delete(row.file_id)
    return Response(status_code=204)


@router.post("/documents/{binding_id}/move", response_model=OfficeDocumentItem)
async def move_document(
    binding_id: str,
    body: OfficeDocumentMoveRequest,
    container: ContainerDep,
) -> OfficeDocumentItem:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    allowed = await container.catalog_repository.user_can_access_catalog(
        body.catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к каталогу")
    source_catalog_id = row.catalog_id
    moved = await container.document_binding_repository.move_to_catalog(
        binding_id,
        ctx.active_company.company_id,
        namespace,
        body.catalog_id,
    )
    if moved is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await record_document_event(
        container,
        binding_id=binding_id,
        company_id=ctx.active_company.company_id,
        event_type="moved",
        user_id=ctx.user.user_id,
        payload={"catalog_id": body.catalog_id},
    )
    try:
        await _unindex_binding_from_catalog(container, source_catalog_id, row.file_id)
        await _index_binding_if_catalog_enabled(container, moved)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    return await binding_to_item(container, moved)


@router.post("/documents/{binding_id}/copy", response_model=OfficeDocumentCreateResponse)
async def copy_document(
    binding_id: str,
    body: OfficeDocumentCopyRequest,
    container: ContainerDep,
) -> OfficeDocumentCreateResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    allowed = await container.catalog_repository.user_can_access_catalog(
        body.catalog_id,
        ctx.active_company.company_id,
        namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к каталогу")
    meta = await container.files_service.get_optional(row.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
    try:
        file_bytes = await s3.download_bytes(meta.s3_key)
    finally:
        await s3.close()
    copy_title = body.title.strip() if body.title is not None else f"{row.title} (copy)"
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(entity_id=namespace),
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
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        catalog_id=body.catalog_id,
        file_id=copied_file.file_id,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        title=copy_title,
        created_by_user_id=ctx.user.user_id,
    )
    await record_document_event(
        container,
        binding_id=created.binding_id,
        company_id=ctx.active_company.company_id,
        event_type="copied",
        user_id=ctx.user.user_id,
        payload={"source_binding_id": binding_id},
    )
    try:
        await _index_binding_if_catalog_enabled(container, created)
    except ServiceClientError as exc:
        raise _http_exception_from_service_client("rag", exc) from exc
    except ValueError as exc:
        raise _http_exception_from_catalog_rag_value_error(exc) from exc
    return OfficeDocumentCreateResponse(
        binding_id=created.binding_id,
        file_id=created.file_id,
        catalog_id=created.catalog_id,
        file_category=created.file_category,
        onlyoffice_document_type=created.onlyoffice_document_type,
        title=created.title,
    )


@router.get("/documents/search", response_model=OfficeDocumentSearchResponse)
async def search_documents(
    container: ContainerDep,
    q: Annotated[str, Query(min_length=1, max_length=500)],
) -> OfficeDocumentSearchResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    rows = await container.document_binding_repository.search_by_title(
        ctx.active_company.company_id,
        namespace,
        q,
    )
    items = await bindings_to_items(container, rows)
    return OfficeDocumentSearchResponse(items=items)


@router.get("/documents/{binding_id}/preview", response_model=OfficeDocumentPreviewResponse)
async def document_preview(
    binding_id: str, container: ContainerDep
) -> OfficeDocumentPreviewResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    meta = await container.files_service.get_optional(row.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    preview_url = await container.viewer_service.preview_for_binding(binding=row, file_record=meta)
    return OfficeDocumentPreviewResponse(binding_id=row.binding_id, preview_url=preview_url)


@router.post("/documents/{binding_id}/shares", response_model=OfficeDocumentShareItem)
async def create_document_share(
    binding_id: str,
    body: OfficeDocumentShareCreateRequest,
    container: ContainerDep,
    request: Request,
) -> OfficeDocumentShareItem:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    permission = body.permission if body.permission in ("view", "edit") else "view"
    patch_body = OfficeResourceAccessPatchRequest(
        link_enabled=True,
        link_permission=permission,
    )
    try:
        if row.link_enabled:
            rotated = await container.office_access_service.rotate_binding_link(row, request)
            public_url = rotated.public_url
        else:
            (
                access_response,
                _raw_token,
            ) = await container.office_access_service.patch_binding_access(
                row,
                patch_body,
                request,
            )
            if access_response.public_url is None:
                raise ValueError("Не удалось создать публичную ссылку")
            public_url = access_response.public_url
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await record_document_event(
        container,
        binding_id=binding_id,
        company_id=ctx.active_company.company_id,
        event_type="shared",
        user_id=ctx.user.user_id,
        payload={"binding_id": binding_id},
    )
    return OfficeDocumentShareItem(
        share_id=binding_id,
        binding_id=binding_id,
        permission=permission,
        share_url=public_url,
        expires_at=None,
        created_at=datetime.now(timezone.utc),
    )


@router.get("/documents/{binding_id}/shares", response_model=OfficeDocumentShareListResponse)
async def list_document_shares(
    binding_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeDocumentShareListResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    shares = await container.document_share_repository.list_for_binding(binding_id)
    base = str(request.base_url).rstrip("/")
    items = [
        OfficeDocumentShareItem(
            share_id=share.share_id,
            binding_id=share.binding_id,
            permission=share.permission,
            share_url=f"{base}/documents/api/v1/shares/<token>",
            expires_at=share.expires_at,
            created_at=share.created_at,
        )
        for share in shares
    ]
    return OfficeDocumentShareListResponse(items=items)


@router.get("/shares/{token}", response_model=OfficeDocumentShareResolveResponse)
async def resolve_document_share(
    token: str, container: ContainerDep
) -> OfficeDocumentShareResolveResponse:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    share = await container.document_share_repository.get_by_token_hash(token_hash)
    if share is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    if share.expires_at is not None and share.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Ссылка истекла")
    row = await container.document_binding_repository.get_by_binding_and_company(
        share.binding_id,
        share.company_id,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return OfficeDocumentShareResolveResponse(
        binding_id=row.binding_id,
        title=row.title,
        permission=share.permission,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
    )


@router.get("/documents/{binding_id}/revisions", response_model=OfficeDocumentRevisionListResponse)
async def list_document_revisions(
    binding_id: str,
    container: ContainerDep,
) -> OfficeDocumentRevisionListResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    revisions = await container.document_revision_repository.list_for_binding(binding_id)
    items = [
        OfficeDocumentRevisionItem(
            revision_id=revision.revision_id,
            revision_number=revision.revision_number,
            file_id=revision.file_id,
            created_by_user_id=revision.created_by_user_id,
            created_at=revision.created_at,
        )
        for revision in revisions
    ]
    return OfficeDocumentRevisionListResponse(items=items)


@router.post("/documents/{binding_id}/revisions", response_model=OfficeDocumentRevisionItem)
async def create_document_revision(
    binding_id: str,
    container: ContainerDep,
) -> OfficeDocumentRevisionItem:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    revision = await container.document_revision_repository.create(
        binding_id=binding_id,
        file_id=row.file_id,
        created_by_user_id=ctx.user.user_id,
    )
    await record_document_event(
        container,
        binding_id=binding_id,
        company_id=ctx.active_company.company_id,
        event_type="revision_created",
        user_id=ctx.user.user_id,
        payload={"revision_id": revision.revision_id},
    )
    return OfficeDocumentRevisionItem(
        revision_id=revision.revision_id,
        revision_number=revision.revision_number,
        file_id=revision.file_id,
        created_by_user_id=revision.created_by_user_id,
        created_at=revision.created_at,
    )


@router.get("/documents/{binding_id}/events", response_model=OfficeDocumentEventListResponse)
async def list_document_events(
    binding_id: str,
    container: ContainerDep,
) -> OfficeDocumentEventListResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    events = await container.document_event_repository.list_for_binding(binding_id)
    items = [
        OfficeDocumentEventItem(
            event_id=event.event_id,
            event_type=event.event_type,
            user_id=event.user_id,
            created_at=event.created_at,
        )
        for event in events
    ]
    return OfficeDocumentEventListResponse(items=items)


@router.get("/documents/{binding_id}/metadata", response_model=OfficeDocumentMetadataResponse)
async def document_metadata(
    binding_id: str, container: ContainerDep
) -> OfficeDocumentMetadataResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    return OfficeDocumentMetadataResponse(binding_id=row.binding_id)


@router.get("/documents/{binding_id}/ai-summary", response_model=OfficeDocumentAiSummaryResponse)
async def document_ai_summary(
    binding_id: str, container: ContainerDep
) -> OfficeDocumentAiSummaryResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    return OfficeDocumentAiSummaryResponse(
        binding_id=row.binding_id,
        summary="",
        enabled=False,
    )


@router.get(
    "/documents/{binding_id}/editor-config",
    response_model=OfficeEditorConfigResponse,
)
async def editor_config(
    binding_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    meta = await container.files_service.get_optional(row.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
    if meta.company_id != ctx.active_company.company_id:
        raise HTTPException(status_code=403, detail="Файл не принадлежит компании")
    user_name = ctx.user.name or ctx.user.email or ctx.user.user_id
    editor_lang = container.viewer_service.default_editor_lang(ctx.language)
    return await container.viewer_service.open_config_for_binding(
        request=request,
        binding=row,
        file_record=meta,
        user_id=ctx.user.user_id,
        user_name=user_name,
        editor_lang=editor_lang,
    )


@router.get("/public/resolve/{token}", response_model=OfficePublicResolveResponse)
async def public_resolve(token: str, container: ContainerDep) -> OfficePublicResolveResponse:
    try:
        target = await container.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await container.office_access_service.build_public_resolve(target)


@router.get("/public/open/{token}", response_model=OfficeEditorConfigResponse)
async def public_open(
    token: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    try:
        target = await container.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if target.kind != "binding" or target.binding is None:
        raise HTTPException(status_code=400, detail="Откройте файл по прямой ссылке")
    meta = await container.files_service.get_optional(target.binding.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != target.binding.company_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    return await container.viewer_service.open_config_for_public_link(
        request=request,
        target=target,
        file_record=meta,
    )


@router.get("/public/catalog/{token}/items", response_model=OfficePublicCatalogItemsResponse)
async def public_catalog_items(
    token: str, container: ContainerDep
) -> OfficePublicCatalogItemsResponse:
    try:
        target = await container.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return await container.office_access_service.list_public_catalog_items(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/public/catalog/{token}/bindings/{binding_id}/open",
    response_model=OfficeEditorConfigResponse,
)
async def public_catalog_binding_open(
    token: str,
    binding_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    try:
        catalog_target = await container.office_access_service.resolve_public_token(token)
        binding = await container.office_access_service.resolve_public_catalog_binding_open(
            catalog_target,
            binding_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    binding_target = PublicLinkTarget(
        kind="binding",
        catalog=None,
        binding=binding,
        token_hash=binding.link_token_hash or "",
    )
    if binding.link_token_hash is None:
        raise HTTPException(status_code=403, detail="Публичная ссылка файла не настроена")
    meta = await container.files_service.get_optional(binding.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return await container.viewer_service.open_config_for_public_link(
        request=request,
        target=binding_target,
        file_record=meta,
    )


@router.get("/office-download")
async def office_download(
    container: ContainerDep,
    token: Annotated[str, Query(description="JWT office_dl")],
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office не настроен")
    try:
        claims = decode_download_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise HTTPException(status_code=401, detail="Недействительный токен скачивания") from e
    file_id = claims.file_id
    company_id = claims.company_id
    binding_id = claims.binding_id
    binding_kind = claims.binding_kind
    if binding_kind == "document":
        binding_row = await container.document_binding_repository.get_by_binding_and_company(
            binding_id,
            company_id,
        )
        if binding_row is None or binding_row.file_id != file_id:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
    elif binding_kind == "file":
        if binding_id != file_viewer_binding_id(file_id):
            raise HTTPException(status_code=403, detail="Доступ запрещён")
    else:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    meta = await container.files_service.get_optional(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != company_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
    try:
        try:
            body = await s3.download_bytes(meta.s3_key)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            logger.warning(
                "office-download: S3 error file_id=%s bucket=%s key=%s code=%s",
                file_id,
                meta.s3_bucket,
                meta.s3_key,
                code,
            )
            raise HTTPException(
                status_code=502,
                detail=f"S3 не отдал объект: {code}",
            ) from e
    finally:
        await s3.close()
    ct = meta.content_type or "application/octet-stream"
    return Response(
        content=body,
        media_type=ct,
        headers={"Content-Disposition": _office_inline_content_disposition(meta.original_name)},
    )


@router.post(
    "/onlyoffice/callback",
    response_model=OnlyOfficeCallbackResponse,
)
async def onlyoffice_callback(
    request: Request,
    container: ContainerDep,
    token: Annotated[str, Query(description="JWT office_cb")],
) -> OnlyOfficeCallbackResponse:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office не настроен")
    try:
        ctx_cb = decode_callback_context_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise HTTPException(status_code=401, detail="Недействительный токен callback") from e
    binding_id = ctx_cb.binding_id
    company_id = ctx_cb.company_id
    binding_kind = ctx_cb.binding_kind

    try:
        raw_body = await request.body()
        body = parse_json_object(raw_body, "OnlyOffice callback body") if raw_body else {}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Callback body must be a JSON object") from exc

    auth = request.headers.get("Authorization")
    bearer = ""
    if auth and auth.startswith("Bearer "):
        bearer = auth[7:].strip()
    else:
        body_token = body.get("token")
        if isinstance(body_token, str) and body_token.strip() != "":
            bearer = body_token.strip()
    if not bearer:
        raise HTTPException(
            status_code=401,
            detail="Ожидается JWT OnlyOffice в Authorization: Bearer или body.token",
        )
    try:
        token_payload = decode_callback_authorization(bearer, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise HTTPException(status_code=401, detail="Недействительный JWT callback") from e
    payload = _onlyoffice_request_payload(token_payload, body)

    namespace = ctx_cb.namespace or ""
    status_raw = payload.get("status")
    if status_raw is None:
        raise HTTPException(status_code=400, detail="Callback status is required")
    if not isinstance(status_raw, str | int):
        raise HTTPException(status_code=400, detail="Callback status must be an integer")
    try:
        status_int = int(status_raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Callback status must be an integer") from None
    logger.info(
        "OnlyOffice callback received binding_id=%s company_id=%s namespace=%s status=%s key=%s",
        binding_id,
        company_id,
        namespace,
        status_int,
        payload.get("key"),
    )

    if status_int in (2, 6):
        url = payload.get("url")
        if not url or not isinstance(url, str):
            raise HTTPException(status_code=400, detail="В callback нет url для сохранения")
        redis_url = get_settings().database.redis_url
        claimed = await try_claim_onlyoffice_callback(
            redis_url,
            binding_id,
            status_int,
            url,
        )
        if not claimed:
            logger.info(
                "OnlyOffice callback: дубликат, пропуск записи binding_id=%s status=%s",
                binding_id,
                status_int,
            )
            return OnlyOfficeCallbackResponse(error=0)

        notification_user_id: str | None = None
        notification_title = "Документ сохранён"
        notification_message = ""
        notification_action_url: str | None = None
        notification_data: JsonObject = {}
        file_id: str
        document_binding: OfficeDocumentBinding | None = None

        if binding_kind == "document":
            document_binding = await container.document_binding_repository.get_for_company(
                binding_id,
                company_id,
                namespace,
            )
            if document_binding is None:
                logger.error(
                    "OnlyOffice callback: привязка %s не найдена (company=%s ns=%s)",
                    binding_id,
                    company_id,
                    namespace,
                )
                raise HTTPException(status_code=404, detail="Привязка не найдена")
            file_id = document_binding.file_id
            notification_user_id = document_binding.created_by_user_id
            notification_message = document_binding.title
            notification_action_url = f"/documents/edit/{binding_id}"
            notification_data = {"binding_id": binding_id, "company_id": company_id}
        elif binding_kind == "file":
            raw_file_id = ctx_cb.file_id
            if raw_file_id is None or raw_file_id == "":
                raise HTTPException(status_code=400, detail="В callback-токене нет file_id")
            file_id = raw_file_id
            if binding_id != file_viewer_binding_id(file_id):
                logger.error(
                    "OnlyOffice callback: некорректный binding_id для file viewer binding_id=%s file_id=%s",
                    binding_id,
                    file_id,
                )
                raise HTTPException(status_code=403, detail="Доступ запрещён")
        else:
            raise HTTPException(status_code=400, detail="Неверный тип привязки OnlyOffice")

        meta = await container.files_service.get_optional(file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")
        if meta.company_id != company_id:
            raise HTTPException(status_code=403, detail="Файл не принадлежит компании")

        async with get_httpx_client(timeout=120.0) as client:
            r = await client.get(url)
            _ = r.raise_for_status()
            new_bytes = r.content
        previous_size = meta.file_size
        previous_checksum = meta.checksum
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
        digest = hashlib.sha256(new_bytes).hexdigest()
        updated = meta.model_copy(
            update={"file_size": len(new_bytes), "checksum": digest},
        )
        _ = await container.files_service.save(updated)
        if document_binding is not None:
            try:
                await _index_binding_if_catalog_enabled_with_job_context(
                    container,
                    document_binding,
                    company_id=company_id,
                    workspace_namespace=namespace,
                    user_id=document_binding.created_by_user_id,
                )
            except ServiceClientError as exc:
                raise _http_exception_from_service_client("rag", exc) from exc
            except ValueError as exc:
                raise _http_exception_from_catalog_rag_value_error(exc) from exc
        logger.info(
            "OnlyOffice callback saved binding_kind=%s binding_id=%s file_id=%s status=%s bytes=%s old_size=%s old_checksum=%s new_checksum=%s",
            binding_kind,
            binding_id,
            file_id,
            status_int,
            len(new_bytes),
            previous_size,
            previous_checksum,
            digest,
        )

        if notification_user_id is not None:
            await notify_user(
                notification_user_id,
                Notification(
                    type=NotificationType.OFFICE_DOCUMENT_SAVED,
                    title=notification_title,
                    message=notification_message,
                    service="office",
                    priority="normal",
                    action_url=notification_action_url,
                    data=notification_data,
                ),
            )

    return OnlyOfficeCallbackResponse(error=0)
