"""
BFF: привязки документов OnlyOffice, выдача JWT редактора, скачивание для DS, callback.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
import jwt
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from apps.office.config import OfficeSettings, get_office_settings
from apps.office.container import OfficeContainer, get_office_container
from apps.office.models.api import (
    OfficeCatalogCreateRequest,
    OfficeCatalogDetailResponse,
    OfficeCatalogListItem,
    OfficeCatalogListResponse,
    OfficeCatalogMemberAddRequest,
    OfficeCatalogMembersResponse,
    OfficeCatalogMemberItem,
    OfficeCatalogPatchRequest,
    OfficeNamespaceCreateRequest,
    OfficeNamespaceCreateResponse,
    OfficeNamespaceItem,
    OfficeNamespaceTemplateItem,
    OfficeNamespacesResponse,
    OfficeDocumentCreateResponse,
    OfficeDocumentItem,
    OfficeDocumentListResponse,
    OfficeDocumentRenameRequest,
    OfficeDocumentRenameResponse,
    OfficeEditorConfigResponse,
    OfficeEmptyCreateRequest,
    OfficeIntegrationStatusResponse,
    OnlyOfficeCallbackResponse,
)
from apps.office.services.callback_dedupe import try_claim_onlyoffice_callback
from apps.office.services.callback_token import (
    decode_callback_context_token,
    encode_callback_context_token,
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
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import get_context
from core.models.identity_models import User
from core.files.s3_client import S3ClientFactory
from core.models.i18n_models import Language
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["office-bff"])

_EMPTY_DOCX = Path(__file__).resolve().parent.parent / "templates" / "empty.docx"

_HUMANITEC_PLATFORM_LOGO_PATH = "/static/core/assets/service_logos/frontend_logo.svg"

_CRM_API_V1_PREFIX = "/crm/api/v1"


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


def _container() -> OfficeContainer:
    return get_office_container()


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


@router.get("/integration/status", response_model=OfficeIntegrationStatusResponse)
async def integration_status() -> OfficeIntegrationStatusResponse:
    ok, detail = _integration_configured()
    return OfficeIntegrationStatusResponse(configured=ok, detail=detail)


@router.get("/namespaces", response_model=OfficeNamespacesResponse)
async def list_namespaces(c: OfficeContainer = Depends(_container)) -> OfficeNamespacesResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    rows = await c.namespace_repository.list_all()
    items: list[OfficeNamespaceItem] = [
        OfficeNamespaceItem(name=ns.name.strip(), is_default=bool(ns.is_default))
        for ns in rows
        if ns.name and ns.name.strip()
    ]
    return OfficeNamespacesResponse(namespaces=items)


@router.get("/namespaces/templates", response_model=list[OfficeNamespaceTemplateItem])
async def list_namespace_templates_proxy(
    c: OfficeContainer = Depends(_container),
) -> list[OfficeNamespaceTemplateItem]:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    path = f"{_CRM_API_V1_PREFIX}/namespaces/templates"
    try:
        raw = await c.service_client.get("crm", path)
    except ServiceClientError as e:
        raise _http_exception_from_service_client("crm", e) from e
    if not isinstance(raw, list):
        raise HTTPException(status_code=502, detail="CRM: неверный формат списка шаблонов namespace")
    out: list[OfficeNamespaceTemplateItem] = []
    for item in raw:
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
    return out


@router.post("/namespaces", response_model=OfficeNamespaceCreateResponse, status_code=201)
async def create_namespace_proxy(
    body: OfficeNamespaceCreateRequest,
    c: OfficeContainer = Depends(_container),
) -> OfficeNamespaceCreateResponse:
    ctx = get_context()
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
        raw = await c.service_client.post("crm", path, json=payload)
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
    c: OfficeContainer = Depends(_container),
) -> list[dict[str, object]]:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    company = await c.company_repository.get(ctx.active_company.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    out: list[dict[str, object]] = []
    for member_user_id, roles in company.members.items():
        u = await c.user_repository.get(member_user_id)
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
async def list_catalogs(c: OfficeContainer = Depends(_container)) -> OfficeCatalogListResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    rows = await c.catalog_repository.list_accessible_with_file_counts(
        company_id=ctx.active_company.company_id,
        namespace=ctx.active_namespace,
        user_id=ctx.user.user_id,
    )
    out: list[OfficeCatalogListItem] = []
    for cat, file_count in rows:
        display_name, avatar_url = await _user_display(c, cat.owner_user_id)
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
    c: OfficeContainer = Depends(_container),
) -> OfficeCatalogDetailResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    cat = await c.catalog_repository.create(
        company_id=ctx.active_company.company_id,
        namespace=ctx.active_namespace,
        title=body.title,
        owner_user_id=ctx.user.user_id,
        is_public=body.is_public,
    )
    display_name, avatar_url = await _user_display(c, cat.owner_user_id)
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
    c: OfficeContainer = Depends(_container),
) -> OfficeCatalogDetailResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    allowed = await c.catalog_repository.user_can_access_catalog(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    cat = await c.catalog_repository.get(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
    )
    if cat is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    display_name, avatar_url = await _user_display(c, cat.owner_user_id)
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
    c: OfficeContainer = Depends(_container),
) -> OfficeCatalogDetailResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    is_owner = await c.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(
            status_code=403,
            detail="Только владелец может изменять каталог",
        )
    updated = await c.catalog_repository.update_catalog(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        title=body.title,
        is_public=body.is_public,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    display_name, avatar_url = await _user_display(c, updated.owner_user_id)
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
    c: OfficeContainer = Depends(_container),
) -> Response:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    is_owner = await c.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может удалить каталог")
    try:
        ok = await c.catalog_repository.delete_catalog(
            catalog_id,
            ctx.active_company.company_id,
            ctx.active_namespace,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    return Response(status_code=204)


@router.get("/catalogs/{catalog_id}/members", response_model=OfficeCatalogMembersResponse)
async def list_catalog_members(
    catalog_id: str,
    c: OfficeContainer = Depends(_container),
) -> OfficeCatalogMembersResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    allowed = await c.catalog_repository.user_can_access_catalog(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        ctx.user.user_id,
    )
    if not allowed:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    cat = await c.catalog_repository.get(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
    )
    if cat is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    member_rows = await c.catalog_repository.list_members(catalog_id)
    member_ids = {m.user_id for m in member_rows}
    member_ids.add(cat.owner_user_id)
    items: list[OfficeCatalogMemberItem] = []
    for uid in sorted(member_ids):
        display_name, avatar_url = await _user_display(c, uid)
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
    c: OfficeContainer = Depends(_container),
) -> OfficeCatalogMembersResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    is_owner = await c.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может добавлять участников")
    try:
        await c.catalog_repository.add_member(
            catalog_id,
            body.user_id.strip(),
            company_id=ctx.active_company.company_id,
            namespace=ctx.active_namespace,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return await list_catalog_members(catalog_id, c)


@router.delete("/catalogs/{catalog_id}/members/{member_user_id}", status_code=204)
async def remove_catalog_member(
    catalog_id: str,
    member_user_id: str,
    c: OfficeContainer = Depends(_container),
) -> Response:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    is_owner = await c.catalog_repository.user_is_owner(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        ctx.user.user_id,
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Только владелец может удалять участников")
    cat = await c.catalog_repository.get(
        catalog_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
    )
    if cat is None:
        raise HTTPException(status_code=404, detail="Каталог не найден")
    if member_user_id == cat.owner_user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить владельца каталога")
    ok = await c.catalog_repository.remove_member(catalog_id, member_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Участник не найден")
    return Response(status_code=204)


@router.get("/documents", response_model=OfficeDocumentListResponse)
async def list_documents(
    catalog_id: str | None = Query(None, min_length=1),
    catalog_ids: list[str] | None = Query(None),
    c: OfficeContainer = Depends(_container),
) -> OfficeDocumentListResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
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
        allowed = await c.catalog_repository.user_can_access_catalog(
            cid,
            ctx.active_company.company_id,
            ctx.active_namespace,
            ctx.user.user_id,
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Нет доступа к каталогу")
    rows = await c.document_binding_repository.list_by_company_namespace_and_catalogs(
        ctx.active_company.company_id,
        ctx.active_namespace,
        resolved_ids,
    )
    user_ids = {r.created_by_user_id for r in rows}
    users_by_id: dict[str, User] = {}
    for uid in user_ids:
        loaded = await c.user_repository.get(uid)
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
    file: UploadFile = File(...),
    title: str | None = Form(None),
    catalog_id: str | None = Form(None),
    c: OfficeContainer = Depends(_container),
) -> OfficeDocumentCreateResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    from core.config import get_settings

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
    fp = c.file_processor
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
        c,
        company_id=ctx.active_company.company_id,
        namespace=ctx.active_namespace,
        user_id=ctx.user.user_id,
        catalog_id=catalog_id,
    )
    row = await c.document_binding_repository.create(
        company_id=ctx.active_company.company_id,
        namespace=ctx.active_namespace,
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
    )


@router.post("/documents/empty", response_model=OfficeDocumentCreateResponse)
async def create_empty_document(
    body: OfficeEmptyCreateRequest,
    c: OfficeContainer = Depends(_container),
) -> OfficeDocumentCreateResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    from core.config import get_settings

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

    fp = c.file_processor
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
        c,
        company_id=ctx.active_company.company_id,
        namespace=ctx.active_namespace,
        user_id=ctx.user.user_id,
        catalog_id=body.catalog_id,
    )
    row = await c.document_binding_repository.create(
        company_id=ctx.active_company.company_id,
        namespace=ctx.active_namespace,
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
    )


@router.patch(
    "/documents/{binding_id}",
    response_model=OfficeDocumentRenameResponse,
)
async def rename_document(
    binding_id: str,
    body: OfficeDocumentRenameRequest,
    c: OfficeContainer = Depends(_container),
) -> OfficeDocumentRenameResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    row = await c.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(c, row, ctx.user.user_id)
    updated = await c.document_binding_repository.update_title(
        binding_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
        body.title.strip(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    return OfficeDocumentRenameResponse(
        binding_id=updated.binding_id,
        title=updated.title,
    )


@router.delete("/documents/{binding_id}", status_code=204)
async def delete_document(binding_id: str, c: OfficeContainer = Depends(_container)) -> Response:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    row = await c.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(c, row, ctx.user.user_id)
    ok = await c.document_binding_repository.delete_binding(
        binding_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
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
    c: OfficeContainer = Depends(_container),
) -> OfficeEditorConfigResponse:
    ctx = get_context()
    if not ctx.active_company:
        raise HTTPException(status_code=403, detail="Компания не выбрана")
    if not ctx.user:
        raise HTTPException(status_code=403, detail="Пользователь не авторизован")
    ok, detail = _integration_configured()
    if not ok:
        raise HTTPException(status_code=503, detail=detail)
    integ = get_office_settings().office
    row = await c.document_binding_repository.get_for_company(
        binding_id,
        ctx.active_company.company_id,
        ctx.active_namespace,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Привязка не найдена")
    await _require_binding_catalog_access(c, row, ctx.user.user_id)
    meta = await c.file_processor.get_file_record(row.file_id)
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
        namespace=ctx.active_namespace,
        secret=integ.jwt_secret,
        ttl_seconds=3600,
    )
    callback_url = f"{base}/documents/api/v1/onlyoffice/callback?token={quote(cb_ctx, safe='')}"

    checksum = meta.checksum or meta.file_id
    doc_key = f"{row.binding_id}_{checksum[:24]}"

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
    token: str = Query(..., description="JWT office_dl"),
    c: OfficeContainer = Depends(_container),
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
    binding_row = await c.document_binding_repository.get_by_binding_and_company(
        binding_id,
        company_id,
    )
    if binding_row is None or binding_row.file_id != file_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    meta = await c.file_processor.get_file_record(file_id)
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
    token: str = Query(..., description="JWT office_cb"),
    c: OfficeContainer = Depends(_container),
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

    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Ожидается Authorization: Bearer (JWT OnlyOffice)")
    bearer = auth[7:].strip()
    try:
        payload = decode_callback_authorization(bearer, integ.jwt_secret)
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Недействительный JWT callback") from e

    status = payload.get("status")
    namespace = ctx_cb["namespace"]
    if status in (2, 6):
        url = payload.get("url")
        if not url or not isinstance(url, str):
            raise HTTPException(status_code=400, detail="В callback нет url для сохранения")
        status_int = int(status)
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

        row = await c.document_binding_repository.get_for_company(
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

        meta = await c.file_processor.get_file_record(row.file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="Файл не найден")

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            new_bytes = r.content
        s3 = await c.file_processor._get_s3_client()
        await s3.upload_bytes(
            data=new_bytes,
            key=meta.s3_key,
            content_type=meta.content_type or "application/octet-stream",
        )
        digest = hashlib.sha256(new_bytes).hexdigest()
        updated = meta.model_copy(
            update={"file_size": len(new_bytes), "checksum": digest},
        )
        await c.file_processor.file_repository.set(updated)

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
