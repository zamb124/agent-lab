"""
BFF: привязки документов OnlyOffice, выдача JWT редактора, скачивание для DS, callback.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from httpx import HTTPError, HTTPStatusError

from apps.office.api.commands import router as office_commands_router
from apps.office.api.data_tables import router as office_data_tables_router
from apps.office.api.viewer_routes import router as office_viewer_router
from apps.office.config import OfficeSettings, get_office_settings
from apps.office.container import OfficeContainer
from apps.office.db.models import OfficeDocumentBinding
from apps.office.dependencies import ContainerDep
from apps.office.events import OFFICE_DOCUMENT_SAVED
from apps.office.models.api import (
    OfficeDocumentEditorSessionResponse,
    OfficeDocumentShareResolveResponse,
    OfficeDocumentSyncRequest,
    OfficeEditorConfigResponse,
    OfficeFileEditorSyncResponse,
    OfficePublicCatalogItemsResponse,
    OfficePublicResolveResponse,
    OnlyOfficeCallbackResponse,
)
from apps.office.services.callback_dedupe import try_claim_onlyoffice_callback
from apps.office.services.callback_token import (
    decode_callback_context_token,
)
from apps.office.services.document_type import supports_onlyoffice_viewer
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from apps.office.services.office_access_service import PublicLinkTarget
from apps.office.services.onlyoffice_jwt import (
    decode_callback_authorization,
    decode_download_token,
)
from core.clients.onlyoffice import OnlyOfficeJwtError, sign_onlyoffice_jwt_hs256
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import Context, clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.events import publish_event_to_user
from core.files.s3_client import S3ClientFactory
from core.http import get_httpx_client
from core.logging import get_log_context, get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.types import JsonObject, parse_json_object, require_json_object
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)
router = APIRouter(tags=["office-bff"])
router.include_router(office_commands_router)
router.include_router(office_viewer_router)
router.include_router(office_data_tables_router)

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
        await _index_binding_if_catalog_enabled(
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


def _http_exception_from_catalog_rag_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if message == "Каталог не найден":
        return HTTPException(status_code=404, detail=message)
    if message == "RAG-индекс для каталога не включён":
        return HTTPException(status_code=409, detail=message)
    if message == "Нет проиндексированных каталогов для поиска":
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=400, detail=message)


async def _require_binding_catalog_access(
    c: OfficeContainer,
    row: OfficeDocumentBinding,
    user_id: str,
) -> None:
    allowed = await c.office_access_service.user_can_view_document(
        row,
        company_id=row.company_id,
        namespace=row.namespace,
        user_id=user_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Нет доступа к каталогу документа")


def _office_inline_content_disposition(original_name: str) -> str:
    name = (original_name or "document").replace("\r", "").replace("\n", "")[:800]
    ascii_fallback = name.encode("ascii", "ignore").decode("ascii").strip() or "document"
    ascii_fallback = ascii_fallback.replace("\\", "_").replace('"', "'")[:200]
    encoded = quote(name, safe="")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _editor_embed_url(file_id: str, namespace: str) -> str:
    return f"/documents/embed/edit/{quote(file_id, safe='')}?namespace={quote(namespace, safe='')}"


def _onlyoffice_document_key(file_id: str, checksum: str | None) -> str:
    """
    ONLYOFFICE `document.key` is a cache/version key, not our document identity.
    Keep identity in `file_id`, and derive the editor key from current file bytes
    so Document Server reloads the real S3 object after every saved change.
    """
    safe_checksum = re.sub(r"[^a-zA-Z0-9_-]", "", checksum or "")[:24]
    if not safe_checksum:
        return file_id
    return f"{file_id}_{safe_checksum}"


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


def _document_mutation_lock_key(file_id: str) -> str:
    return f"office:document:{file_id}:mutation"


def _document_mutation_lock_release_channel(file_id: str) -> str:
    return f"office:document:{file_id}:mutation:released"


@asynccontextmanager
async def _document_mutation_lock(
    container: OfficeContainer,
    file_id: str,
    *,
    wait_timeout_seconds: float = 45.0,
):
    """
    Distributed mutation lock на документ через Redis SET NX EX.

    Ожидание освобождения — pub/sub: при release lock публикуется в канал
    ``office:document:<file_id>:mutation:released``. Это убирает busy-loop
    с ``asyncio.sleep(0.25)`` (по 4 TCP-roundtrip в секунду на каждый запрос
    в очереди). Fallback poll каждые ``_LOCK_FALLBACK_POLL_SECONDS`` сохранён
    на случай, если release произошёл до подписки или сообщение было потеряно.
    """
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
    file_id: str,
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
            "OnlyOffice command failed before mutation file_id=%s command=%s http_status=%s response=%s",
            file_id,
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
            "OnlyOffice command failed before mutation file_id=%s command=%s http_status=%s response=%s",
            file_id,
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


async def _force_save_open_editor_if_needed(
    *,
    file_id: str,
    document_key: str,
) -> int | None:
    code = await _post_onlyoffice_command(
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
    raise HTTPException(
        status_code=409, detail=f"OnlyOffice forcesave failed: error={code} ({detail})"
    )


async def _drop_open_editor_sessions(
    *,
    file_id: str,
    document_key: str,
) -> None:
    code = await _post_onlyoffice_command(
        payload={"c": "drop", "key": document_key},
        file_id=file_id,
        command_name="drop",
    )
    if code is None or code in (0, 1):
        return
    detail = _ONLYOFFICE_COMMAND_ERROR_DETAILS.get(code, "unknown error")
    raise HTTPException(status_code=409, detail=f"OnlyOffice drop failed: error={code} ({detail})")


async def _wait_for_file_change_after_forcesave(
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
            raise HTTPException(status_code=404, detail="Файл не найден")
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
        raise HTTPException(
            status_code=409, detail="Не удалось дождаться сохранения открытого редактора"
        )
    return False


async def _require_explicit_namespace(container: OfficeContainer) -> str:
    """
    Жёсткая привязка documents к namespace.

    Каталоги и документы Office живут строго внутри одного workspace, и
    BFF не допускает «все пространства» / неявный fallback. Возвращает имя
    проверенного namespace, чтобы вызывающий мог использовать его явно.

    Системный `default` всегда валиден и при необходимости создаётся через
    `NamespaceService.ensure_default()` (тот же механизм, что и в публичном
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
        _ = await container.namespace_service.ensure_default()
    found = await container.namespace_service.get(raw)
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
    binding = await container.document_binding_repository.get_by_file_and_company(
        file_id,
        ctx.active_company.company_id,
    )
    namespace: str | None = None
    if binding is not None and binding.namespace.strip():
        namespace = binding.namespace
    elif ctx.active_namespace is not None and ctx.active_namespace.strip():
        namespace = ctx.active_namespace.strip()
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
        namespace=namespace,
    )


@router.post("/files/{file_id}/sync", response_model=OfficeFileEditorSyncResponse)
async def sync_file_editor_state(
    file_id: str,
    container: ContainerDep,
    body: OfficeDocumentSyncRequest | None = None,
) -> OfficeFileEditorSyncResponse:
    ctx = _require_office_context()
    sync_options = body or OfficeDocumentSyncRequest()
    async with _document_mutation_lock(container, file_id):
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
        document_key = _onlyoffice_document_key(file_id, meta.checksum)
        if sync_options.settle_ms > 0:
            await asyncio.sleep(sync_options.settle_ms / 1000)
        force_code = await _force_save_open_editor_if_needed(
            file_id=file_id,
            document_key=document_key,
        )
        if sync_options.close and force_code == 4:
            await asyncio.sleep(1.5)
            force_code = await _force_save_open_editor_if_needed(
                file_id=file_id,
                document_key=document_key,
            )
        logger.info(
            "OnlyOffice file sync command result file_id=%s close=%s dirty=%s force_code=%s",
            file_id,
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
            _ = await _wait_for_file_change_after_forcesave(
                container=container,
                file_id=file_id,
                previous_checksum=meta.checksum,
                previous_file_size=meta.file_size,
            )
            meta = await container.files_service.get_optional(file_id)
            if meta is None:
                raise HTTPException(status_code=404, detail="Файл не найден")
        if sync_options.close and force_code in (0, 4):
            await _drop_open_editor_sessions(
                file_id=file_id,
                document_key=document_key,
            )
    return OfficeFileEditorSyncResponse(
        file_id=meta.file_id,
        checksum=meta.checksum,
        file_size=meta.file_size,
    )


@router.post(
    "/documents/{file_id}/sync",
    response_model=OfficeDocumentEditorSessionResponse,
)
async def sync_document_editor_state(
    file_id: str,
    container: ContainerDep,
    body: OfficeDocumentSyncRequest | None = None,
) -> OfficeDocumentEditorSessionResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    sync_options = body or OfficeDocumentSyncRequest()
    async with _document_mutation_lock(container, file_id):
        row = await container.document_binding_repository.get(
            file_id,
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
                file_id=row.file_id,
                catalog_id=row.catalog_id,
                title=row.title,
                file_category=row.file_category,
                onlyoffice_document_type=row.onlyoffice_document_type,
                namespace=namespace,
                editor_url=_editor_embed_url(row.file_id, namespace),
            )

        document_key = _onlyoffice_document_key(row.file_id, meta.checksum)
        if sync_options.settle_ms > 0:
            await asyncio.sleep(sync_options.settle_ms / 1000)
        force_code = await _force_save_open_editor_if_needed(
            file_id=row.file_id,
            document_key=document_key,
        )
        if sync_options.close and force_code == 4:
            await asyncio.sleep(1.5)
            force_code = await _force_save_open_editor_if_needed(
                file_id=row.file_id,
                document_key=document_key,
            )
        logger.info(
            "OnlyOffice sync command result file_id=%s close=%s dirty=%s force_code=%s",
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
            _ = await _wait_for_file_change_after_forcesave(
                container=container,
                file_id=row.file_id,
                previous_checksum=meta.checksum,
                previous_file_size=meta.file_size,
            )
        if sync_options.close and force_code in (0, 4):
            await _drop_open_editor_sessions(
                file_id=row.file_id,
                document_key=document_key,
            )

    return OfficeDocumentEditorSessionResponse(
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        title=row.title,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        namespace=namespace,
        editor_url=_editor_embed_url(row.file_id, namespace),
    )


@router.get(
    "/documents/{file_id}/editor-config",
    response_model=OfficeEditorConfigResponse,
)
async def editor_config(
    file_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    row = await container.document_binding_repository.get(
        file_id,
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


@router.get("/shares/{token}", response_model=OfficeDocumentShareResolveResponse)
async def resolve_document_share(
    token: str, container: ContainerDep
) -> OfficeDocumentShareResolveResponse:
    try:
        target = await container.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if target.kind != "binding" or target.binding is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    row = target.binding
    if row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    if row.link_permission not in ("viewer", "editor"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid link_permission: {row.link_permission}",
        )
    return OfficeDocumentShareResolveResponse(
        file_id=row.file_id,
        title=row.title,
        permission=row.link_permission,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
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
    "/public/catalog/{token}/files/{file_id}/open",
    response_model=OfficeEditorConfigResponse,
)
async def public_catalog_binding_open(
    token: str,
    file_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    try:
        catalog_target = await container.office_access_service.resolve_public_token(token)
        binding = await container.office_access_service.resolve_public_catalog_binding_open(
            catalog_target,
            file_id,
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
    viewer_scope = claims.viewer_scope
    if viewer_scope == "catalog":
        binding_row = await container.document_binding_repository.get_by_file_and_company(
            file_id,
            company_id,
        )
        if binding_row is None:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
    elif viewer_scope != "file":
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
    file_id = ctx_cb.file_id
    company_id = ctx_cb.company_id
    viewer_scope = ctx_cb.viewer_scope

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
        "OnlyOffice callback received file_id=%s company_id=%s namespace=%s status=%s key=%s",
        file_id,
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
            file_id,
            status_int,
            url,
        )
        if not claimed:
            logger.info(
                "OnlyOffice callback: дубликат, пропуск записи file_id=%s status=%s",
                file_id,
                status_int,
            )
            return OnlyOfficeCallbackResponse(error=0)

        notification_user_id: str | None = None
        notification_title = "Документ сохранён"
        notification_message = ""
        notification_action_url: str | None = None
        notification_data: JsonObject = {}
        document_binding: OfficeDocumentBinding | None = None

        if viewer_scope == "catalog":
            document_binding = await container.document_binding_repository.get_by_file_and_company(
                file_id,
                company_id,
            )
            if document_binding is None:
                logger.error(
                    "OnlyOffice callback: привязка %s не найдена (company=%s)",
                    file_id,
                    company_id,
                )
                raise HTTPException(status_code=404, detail="Привязка не найдена")
            notification_user_id = document_binding.created_by_user_id
            notification_message = document_binding.title
            notification_action_url = f"/documents/edit/{file_id}"
            notification_data = {"file_id": file_id, "company_id": company_id}
        elif viewer_scope != "file":
            raise HTTPException(status_code=400, detail="Неверный viewer_scope OnlyOffice")

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
            "OnlyOffice callback saved viewer_scope=%s file_id=%s status=%s bytes=%s old_size=%s old_checksum=%s new_checksum=%s",
            viewer_scope,
            file_id,
            status_int,
            len(new_bytes),
            previous_size,
            previous_checksum,
            digest,
        )

        if notification_user_id is not None:
            await publish_event_to_user(
                notification_user_id,
                OFFICE_DOCUMENT_SAVED,
                {
                    "file_id": file_id,
                    "company_id": company_id,
                    "title": notification_message,
                },
                company_id=company_id,
            )
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
