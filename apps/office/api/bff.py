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
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import jwt
from botocore.exceptions import ClientError
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError

from apps.office.config import OfficeSettings, get_office_settings
from apps.office.container import OfficeContainer
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
    OfficeDocumentAppendTextRequest,
    OfficeDocumentCreateResponse,
    OfficeDocumentEditorSessionResponse,
    OfficeDocumentFromFileRequest,
    OfficeDocumentItem,
    OfficeDocumentListResponse,
    OfficeDocumentMutationResponse,
    OfficeDocumentRenameRequest,
    OfficeDocumentRenameResponse,
    OfficeDocumentReplaceTextRequest,
    OfficeDocumentSyncRequest,
    OfficeEditorConfigResponse,
    OfficeEmptyCreateRequest,
    OfficeIntegrationStatusResponse,
    OfficeNamespaceCreateRequest,
    OfficeNamespaceCreateResponse,
    OfficeNamespaceItem,
    OfficeNamespaceTemplateItem,
    OfficeSpreadsheetUpdateCellsRequest,
    OnlyOfficeCallbackResponse,
)
from apps.office.services.callback_dedupe import try_claim_onlyoffice_callback
from apps.office.services.callback_token import (
    decode_callback_context_token,
    encode_callback_context_token,
)
from apps.office.services.document_mutations import (
    DocumentMutationError,
    append_text_to_document,
    replace_text_in_document,
    update_spreadsheet_cells,
)
from apps.office.services.document_type import (
    onlyoffice_document_type_for_upload,
    onlyoffice_file_type_for_binding,
    resolve_onlyoffice_document_type_for_editor,
)
from apps.office.services.minimal_ooxml import minimal_pptx_bytes, minimal_xlsx_bytes
from apps.office.services.onlyoffice_jwt import (
    decode_callback_authorization,
    decode_download_token,
    encode_download_token,
    encode_editor_config,
)
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import Context, get_context
from core.files.s3_client import S3ClientFactory
from core.http import get_httpx_client
from core.logging import get_logger
from core.models.i18n_models import Language
from core.models.identity_models import Company, User
from core.pagination import OffsetPage
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)
router = APIRouter(tags=["office-bff"])

_EMPTY_DOCX = Path(__file__).resolve().parent.parent / "templates" / "empty.docx"

_HUMANITEC_PLATFORM_LOGO_PATH = "/static/core/assets/service_logos/frontend_logo.svg"

_CRM_API_V1_PREFIX = "/crm/api/v1"


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
    if ctx.user is None:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
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
    row,
    user_id: str,
) -> None:
    allowed = await c.catalog_repository.user_can_access_catalog(
        row.catalog_id,
        row.company_id,
        row.namespace,
        user_id,
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
        f"/documents/embed/edit/{quote(binding_id, safe='')}"
        f"?namespace={quote(namespace, safe='')}"
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

def _onlyoffice_request_payload(token_payload: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """
    ONLYOFFICE can sign callback/command parameters directly or wrap them in {"payload": {...}}.
    Header JWT uses the wrapper in current docs; body JWT often signs the parameters directly.
    """
    wrapped = token_payload.get("payload")
    if isinstance(wrapped, dict):
        return wrapped
    if "status" in token_payload or "url" in token_payload or "key" in token_payload:
        return token_payload
    if "status" in body or "url" in body or "key" in body:
        return body
    return token_payload

@asynccontextmanager
async def _document_mutation_lock(binding_id: str, *, wait_timeout_seconds: float = 45.0):
    redis_url = get_settings().database.redis_url
    lock_key = f"office:document:{binding_id}:mutation"
    token = uuid.uuid4().hex
    client = RedisClient(redis_url)
    deadline = asyncio.get_running_loop().time() + wait_timeout_seconds
    ok = False
    try:
        while True:
            ok = await client.set_nx(lock_key, token, 120)
            if ok:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise HTTPException(status_code=409, detail="Документ уже изменяется")
            await asyncio.sleep(0.25)
    except Exception:
        await client.close()
        raise
    try:
        yield
    finally:
        await client.delete(lock_key)
        await client.close()

_ONLYOFFICE_COMMAND_ERROR_DETAILS = {
    1: "document key is missing or no open document with this key was found",
    2: "callback URL is not correct or is not reachable from Document Server",
    3: "internal Document Server error",
    4: "no changes were applied before forcesave",
    5: "command is not correct",
    6: "invalid Document Server JWT token",
}

def _document_server_command_base_url(settings: OfficeSettings) -> str:
    dev_upstream = (settings.server.document_server_dev_upstream_url or "").strip().rstrip("/")
    if settings.server.env in ("development", "test") and dev_upstream:
        return dev_upstream
    return settings.office.document_server_public_url.strip().rstrip("/")

async def _post_onlyoffice_command(
    *,
    payload: dict[str, object],
    binding_id: str,
    command_name: str,
    timeout: float = 10.0,
) -> int | None:
    settings = get_office_settings()
    integ = settings.office
    ds = _document_server_command_base_url(settings)
    if not ds:
        return None
    body = {"token": jwt.encode(payload, integ.jwt_secret, algorithm="HS256")}
    key = str(payload.get("key") or "").strip()
    url = f"{ds}/command"
    if key:
        url = f"{url}?shardkey={quote(key, safe='')}"
    try:
        async with get_httpx_client(timeout=timeout) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        response_preview = ""
        if response is not None:
            response_preview = str(getattr(response, "text", "") or "")[:500]
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
    if not isinstance(data, dict):
        raise HTTPException(status_code=409, detail=f"OnlyOffice {command_name} returned invalid response")
    code = int(data.get("error", -1) or 0)
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
    raise HTTPException(status_code=409, detail=f"OnlyOffice forcesave failed: error={code} ({detail})")

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
        meta = await container.file_processor.get_file_record(file_id)
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
    raise HTTPException(status_code=409, detail="Не удалось дождаться сохранения открытого редактора")

def _editor_header_brand_base_url(settings: OfficeSettings) -> str:
    """Origin для логотипа в шапке OnlyOffice (браузер пользователя, не host.docker.internal)."""
    ec = settings.office.editor_customization
    manual = ec.branding_public_base_url.strip().rstrip("/")
    if manual:
        return manual
    srv = settings.server
    # platform_public_base_url — публичный origin; office_service_url в Docker часто http://office:8008 (только внутри сети).
    for candidate in (srv.platform_public_base_url, srv.frontend_service_url, srv.office_service_url):
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip().rstrip("/")
    return ""

def _onlyoffice_editor_customization_payload() -> dict[str, object]:
    settings = get_office_settings()
    ec = settings.office.editor_customization
    customization: dict[str, object] = {
        "compactToolbar": ec.compact_toolbar,
        "compactHeader": ec.compact_header,
        "uiTheme": ec.ui_theme,
        "features": {"featuresTips": ec.features_tips},
    }
    image = ec.logo_image_url.strip()
    link_explicit = ec.logo_link_url.strip()
    if image:
        logo: dict[str, object] = {"image": image}
        dark = ec.logo_image_dark_url.strip()
        if dark:
            logo["imageDark"] = dark
        logo["url"] = link_explicit if link_explicit else ""
        customization["logo"] = logo
    elif ec.platform_header_branding:
        origin = _editor_header_brand_base_url(settings)
        if origin:
            static_logo = f"{origin}{_HUMANITEC_PLATFORM_LOGO_PATH}"
            customization["logo"] = {
                "image": static_logo,
                "imageDark": static_logo,
                "url": link_explicit if link_explicit else f"{origin}/documents",
            }
            parsed = urlparse(origin)
            www = parsed.netloc if parsed.netloc else origin
            customization["customer"] = {"name": "HUMANITEC", "www": www}
    return customization

def _integration_configured() -> tuple[bool, str]:
    s = get_office_settings().office
    if not s.jwt_secret.strip():
        return False, "Не задан office.jwt_secret (совпадает с JWT_SECRET Document Server)"
    if not s.document_server_public_url.strip():
        return False, "Не задан office.document_server_public_url"
    if not s.callback_public_base_url.strip():
        return False, "Не задан office.callback_public_base_url (доступен с контейнера Document Server)"
    return True, ""

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
        await container.namespace_repository.list(limit=1)
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
async def integration_status(container: ContainerDep) -> OfficeIntegrationStatusResponse:
    ok, detail = _integration_configured()
    return OfficeIntegrationStatusResponse(configured=ok, detail=detail)

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
    return OffsetPage[OfficeNamespaceItem](items=items, total=len(items), limit=len(items), offset=0)

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
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        raise HTTPException(status_code=502, detail="CRM: неверный формат списка шаблонов namespace")
    raw_items = raw["items"]
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
    return OffsetPage[OfficeNamespaceTemplateItem](items=out, total=len(out), limit=len(out), offset=0)

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
) -> list[dict[str, object]]:
    ctx = _require_office_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    company = await container.company_repository.get(ctx.active_company.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    out: list[dict[str, object]] = []
    for member_user_id, roles in company.members.items():
        u = await container.user_repository.get(member_user_id)
        if u is None:
            continue
        member_email = u.emails[0] if u.emails else None
        roles_list = roles if isinstance(roles, list) else [roles]
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
                title=cat.title,
                file_count=file_count,
                owner_user_id=cat.owner_user_id,
                owner_display_name=display_name,
                owner_avatar_url=avatar_url,
                is_owner=cat.owner_user_id == ctx.user.user_id,
                is_public=cat.is_public,
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
    cat = await container.catalog_repository.create(
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        title=body.title,
        owner_user_id=ctx.user.user_id,
        is_public=body.is_public,
    )
    display_name, avatar_url = await _user_display(container, cat.owner_user_id)
    return OfficeCatalogDetailResponse(
        catalog_id=cat.catalog_id,
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
        await container.catalog_repository.add_member(
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

@router.get("/documents", response_model=OfficeDocumentListResponse)
async def list_documents(
    container: ContainerDep,
    catalog_id: str | None = Query(None, min_length=1),
    catalog_ids: list[str] | None = Query(None),
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
    user_ids = {r.created_by_user_id for r in rows}
    users_by_id: dict[str, User] = {}
    for uid in user_ids:
        loaded = await container.user_repository.get(uid)
        if loaded is not None:
            users_by_id[uid] = loaded

    items: list[OfficeDocumentItem] = []
    for r in rows:
        author = users_by_id.get(r.created_by_user_id)
        if author is not None:
            display_name = author.name
            avatar_url = author.avatar_url
        else:
            display_name = r.created_by_user_id
            avatar_url = None
        items.append(
            OfficeDocumentItem(
                binding_id=r.binding_id,
                catalog_id=r.catalog_id,
                title=r.title,
                file_id=r.file_id,
                document_type=r.document_type,
                created_at=r.created_at,
                created_by_user_id=r.created_by_user_id,
                created_by_display_name=display_name,
                created_by_avatar_url=avatar_url,
            )
        )
    return OfficeDocumentListResponse(items=items)

@router.post("/documents", response_model=OfficeDocumentCreateResponse)
async def upload_document(
    container: ContainerDep,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    catalog_id: str | None = Form(None),
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
    try:
        document_type, _ = onlyoffice_document_type_for_upload(
            raw_name,
            guessed_ct.split(";")[0].strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    fp = container.file_processor
    prefix = "/documents/api/v1/files/download"
    meta = await fp.persist_uploaded_file(
        data=data,
        original_name=raw_name,
        content_type=guessed_ct.split(";")[0].strip(),
        uploaded_by=ctx.user.user_id,
        company_id=ctx.active_company.company_id,
        public=False,
        download_url_prefix=prefix,
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
        document_type=document_type,
        title=doc_title,
        created_by_user_id=ctx.user.user_id,
    )
    return OfficeDocumentCreateResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        document_type=row.document_type,
        title=row.title,
        editor_url=_editor_embed_url(row.binding_id, namespace),
    )

@router.post("/documents/from-file", response_model=OfficeDocumentCreateResponse)
async def open_existing_file_as_document(
    body: OfficeDocumentFromFileRequest,
    container: ContainerDep,
) -> OfficeDocumentCreateResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    file_id = body.file_id.strip()
    meta = await container.file_processor.get_file_record(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != ctx.active_company.company_id:
        raise HTTPException(status_code=403, detail="Файл не принадлежит компании")

    try:
        document_type, _ = onlyoffice_document_type_for_upload(
            meta.original_name,
            (meta.content_type or "application/octet-stream").split(";")[0].strip(),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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
            document_type=existing.document_type,
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
            document_type=document_type,
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
            document_type=existing.document_type,
            title=existing.title,
            editor_url=_editor_embed_url(existing.binding_id, namespace),
        )
    return OfficeDocumentCreateResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        document_type=row.document_type,
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
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        document_type = "word"
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
        document_type = "cell"
    else:
        data = minimal_pptx_bytes()
        original_name = f"{stem}.pptx"
        content_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        document_type = "slide"

    fp = container.file_processor
    prefix = "/documents/api/v1/files/download"
    meta = await fp.persist_uploaded_file(
        data=data,
        original_name=original_name,
        content_type=content_type,
        uploaded_by=ctx.user.user_id,
        company_id=ctx.active_company.company_id,
        public=False,
        download_url_prefix=prefix,
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
        document_type=document_type,
        title=body.title.strip(),
        created_by_user_id=ctx.user.user_id,
    )
    return OfficeDocumentCreateResponse(
        binding_id=row.binding_id,
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        document_type=row.document_type,
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
        document_type=row.document_type,
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
    async with _document_mutation_lock(binding_id):
        row = await container.document_binding_repository.get_for_company(
            binding_id,
            ctx.active_company.company_id,
            namespace,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Привязка не найдена")
        await _require_binding_catalog_access(container, row, ctx.user.user_id)
        meta = await container.file_processor.get_file_record(row.file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")

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
        document_type=row.document_type,
        namespace=namespace,
        editor_url=_editor_embed_url(row.binding_id, namespace),
    )

async def _apply_document_bytes_mutation(
    *,
    binding_id: str,
    container: OfficeContainer,
    mutate,
    changed_count: int | None = None,
    tool_call_id: str | None = None,
) -> OfficeDocumentMutationResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    async with _document_mutation_lock(binding_id):
        row = await container.document_binding_repository.get_for_company(
            binding_id,
            ctx.active_company.company_id,
            namespace,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Привязка не найдена")
        await _require_binding_catalog_access(container, row, ctx.user.user_id)
        meta = await container.file_processor.get_file_record(row.file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")
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
            meta = await container.file_processor.get_file_record(row.file_id)
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
        if not isinstance(new_bytes, bytes):
            raise HTTPException(status_code=500, detail="Mutation returned invalid bytes")
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
            await s3.upload_bytes(
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
        await container.file_processor.file_repository.set(updated_meta)
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
        tool_call_id=body.tool_call_id,
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
        tool_call_id=body.tool_call_id,
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
        tool_call_id=body.tool_call_id,
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
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    ok = await container.document_binding_repository.delete_binding(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    return Response(status_code=204)

@router.get(
    "/documents/{binding_id}/editor-config",
    response_model=OfficeEditorConfigResponse,
)
async def editor_config(
    binding_id: str,
    container: ContainerDep,
) -> OfficeEditorConfigResponse:
    namespace = await _require_explicit_namespace(container)
    ctx = _require_office_context()
    ok, detail = _integration_configured()
    if not ok:
        raise HTTPException(status_code=503, detail=detail)
    integ = get_office_settings().office
    row = await container.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(container, row, ctx.user.user_id)
    meta = await container.file_processor.get_file_record(row.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
    if meta.company_id != ctx.active_company.company_id:
        raise HTTPException(status_code=403, detail="Файл не принадлежит компании")

    base = integ.callback_public_base_url.rstrip("/")
    dl = encode_download_token(
        file_id=row.file_id,
        company_id=ctx.active_company.company_id,
        binding_id=row.binding_id,
        secret=integ.jwt_secret,
        ttl_seconds=integ.download_token_ttl_seconds,
    )
    download_url = f"{base}/documents/api/v1/office-download?token={quote(dl, safe='')}"
    cb_ctx = encode_callback_context_token(
        binding_id=row.binding_id,
        company_id=ctx.active_company.company_id,
        namespace=namespace,
        secret=integ.jwt_secret,
        ttl_seconds=3600,
    )
    callback_url = f"{base}/documents/api/v1/onlyoffice/callback?token={quote(cb_ctx, safe='')}"

    doc_key = _onlyoffice_document_key(row.binding_id, meta.checksum)

    editor_document_type = resolve_onlyoffice_document_type_for_editor(
        row.document_type,
        meta.original_name,
    )
    file_type = onlyoffice_file_type_for_binding(editor_document_type, meta.original_name)
    user_name = ctx.user.name or ctx.user.email or ctx.user.user_id
    editor_lang = ctx.language.value if ctx.language else Language.EN.value
    config = {
        "type": "desktop",
        "width": "100%",
        "height": "100%",
        "document": {
            "fileType": file_type,
            "key": doc_key,
            "title": row.title,
            "url": download_url,
            "permissions": {
                "comment": True,
                "copy": True,
                "download": True,
                "edit": True,
                "fillForms": True,
                "modifyContentControl": True,
                "modifyFilter": True,
                "print": True,
                "review": True,
            },
        },
        "documentType": editor_document_type,
        "editorConfig": {
            "mode": "edit",
            "callbackUrl": callback_url,
            "user": {"id": ctx.user.user_id, "name": user_name},
            "lang": editor_lang,
            "coEditing": {"mode": "fast"},
            "customization": _onlyoffice_editor_customization_payload(),
        },
    }
    token = encode_editor_config(config, integ.jwt_secret)
    ds = integ.document_server_public_url.rstrip("/")
    return OfficeEditorConfigResponse(document_server_url=ds, token=token)

@router.get("/office-download")
async def office_download(
    container: ContainerDep,
    token: str = Query(..., description="JWT office_dl"),
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office не настроен")
    try:
        claims = decode_download_token(token, integ.jwt_secret)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Недействительный токен скачивания") from e
    file_id = claims["file_id"]
    company_id = claims["company_id"]
    binding_id = claims["binding_id"]
    binding_row = await container.document_binding_repository.get_by_binding_and_company(
        binding_id,
        company_id,
    )
    if binding_row is None or binding_row.file_id != file_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    meta = await container.file_processor.get_file_record(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != company_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
    try:
        try:
            body = await s3.download_bytes(meta.s3_key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            logger.warning(
                "office-download: S3 error file_id=%s bucket=%s key=%s code=%s",
                file_id,
                meta.s3_bucket,
                meta.s3_key,
                code,
            )
            raise HTTPException(
                status_code=502,
                detail=f"S3 не отдал объект: {code or 'unknown'}",
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
    token: str = Query(..., description="JWT office_cb"),
) -> OnlyOfficeCallbackResponse:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office не настроен")
    try:
        ctx_cb = decode_callback_context_token(token, integ.jwt_secret)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Недействительный токен callback") from e
    binding_id = ctx_cb["binding_id"]
    company_id = ctx_cb["company_id"]

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    auth = request.headers.get("Authorization")
    bearer = ""
    if auth and auth.startswith("Bearer "):
        bearer = auth[7:].strip()
    elif isinstance(body.get("token"), str) and str(body.get("token")).strip():
        bearer = str(body["token"]).strip()
    if not bearer:
        raise HTTPException(status_code=401, detail="Ожидается JWT OnlyOffice в Authorization: Bearer или body.token")
    try:
        token_payload = decode_callback_authorization(bearer, integ.jwt_secret)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Недействительный JWT callback") from e
    payload = _onlyoffice_request_payload(token_payload, body)

    namespace = ctx_cb["namespace"]
    try:
        status_int = int(payload.get("status"))
    except (TypeError, ValueError):
        status_int = 0
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

        row = await container.document_binding_repository.get_for_company(
            binding_id,
            company_id,
            namespace,
        )
        if row is None:
            logger.error(
                "OnlyOffice callback: привязка %s не найдена (company=%s ns=%s)",
                binding_id,
                company_id,
                namespace,
            )
            raise HTTPException(status_code=404, detail="Привязка не найдена")

        meta = await container.file_processor.get_file_record(row.file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")

        async with get_httpx_client(timeout=120.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            new_bytes = r.content
        previous_size = meta.file_size
        previous_checksum = meta.checksum
        s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
        try:
            await s3.upload_bytes(
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
        await container.file_processor.file_repository.set(updated)
        logger.info(
            "OnlyOffice callback saved binding_id=%s file_id=%s status=%s bytes=%s old_size=%s old_checksum=%s new_checksum=%s",
            binding_id,
            row.file_id,
            status_int,
            len(new_bytes),
            previous_size,
            previous_checksum,
            digest,
        )

        await notify_user(
            row.created_by_user_id,
            Notification(
                type=NotificationType.OFFICE_DOCUMENT_SAVED,
                title="Документ сохранён",
                message=row.title,
                service="office",
                priority="normal",
                action_url=f"/documents/edit/{binding_id}",
                data={"binding_id": binding_id, "company_id": company_id},
            ),
        )

    return OnlyOfficeCallbackResponse(error=0)
