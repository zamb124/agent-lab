"""Orchestration viewer handlers для office BFF."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from apps.office.config import get_office_settings
from apps.office.db.models import OfficeDocumentBinding
from apps.office.services.document_type import supports_onlyoffice_viewer
from apps.office.services.office_access_service import PublicLinkTarget
from apps.office.services.viewer_context import OfficeViewerLinkPermission, ViewerOpenContext
from apps.office.services.viewer_handlers.binary_handler import BinaryViewerHandler
from apps.office.services.viewer_handlers.image_handler import ImageViewerHandler
from apps.office.services.viewer_handlers.media_handler import MediaViewerHandler
from apps.office.services.viewer_handlers.onlyoffice_handler import OnlyOfficeViewerHandler
from apps.office.services.viewer_handlers.text_handler import TextViewerHandler
from core.documents.viewer.models import (
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
)
from core.documents.viewer.resolver import resolve_viewer_handler_id
from core.files.models import FileRecord
from core.middleware.auth.company_resolver import build_service_base_url
from core.models.i18n_models import Language

_LOCAL_DOCUMENT_SERVER_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_OfficeViewerHandler = (
    OnlyOfficeViewerHandler
    | ImageViewerHandler
    | MediaViewerHandler
    | TextViewerHandler
    | BinaryViewerHandler
)


def file_viewer_binding_id(file_id: str) -> str:
    digest = hashlib.sha256(file_id.encode("utf-8")).hexdigest()[:40]
    return f"file_{digest}"


def integration_configured() -> tuple[bool, str]:
    settings = get_office_settings().office
    if not settings.jwt_secret.strip():
        return False, "Не задан office.jwt_secret (совпадает с JWT_SECRET Document Server)"
    if not settings.document_server_public_url.strip():
        return False, "Не задан office.document_server_public_url"
    if not settings.callback_public_base_url.strip():
        return False, "Не задан office.callback_public_base_url (доступен с контейнера Document Server)"
    return True, ""


def _request_public_scheme(request: Request) -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    if forwarded_proto in {"http", "https"}:
        return forwarded_proto
    return request.url.scheme


def browser_public_base_url(request: Request) -> str:
    return build_service_base_url(request)


def browser_document_server_url(raw_url: str, request: Request) -> str:
    value = raw_url.strip().rstrip("/")
    if not value:
        raise ValueError("document_server_public_url пуст")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in _LOCAL_DOCUMENT_SERVER_HOSTS:
        scheme = _request_public_scheme(request)
        port = request.url.port
        netloc = request.url.netloc
        if port and f":{port}" not in netloc:
            netloc = f"{request.url.hostname}:{port}"
        return f"{scheme}://{netloc}".rstrip("/")
    if (
        _request_public_scheme(request) == "https"
        and parsed.scheme == "http"
        and host not in _LOCAL_DOCUMENT_SERVER_HOSTS
    ):
        return parsed._replace(scheme="https").geturl().rstrip("/")
    return value


class DocumentViewerService:
    def __init__(self) -> None:
        self._handlers: dict[DocumentViewerHandlerId, _OfficeViewerHandler] = {
            "onlyoffice": OnlyOfficeViewerHandler(),
            "image": ImageViewerHandler(),
            "media": MediaViewerHandler(),
            "text": TextViewerHandler(),
            "binary": BinaryViewerHandler(),
        }

    def resolve_handler_id(
        self,
        *,
        file_category: str,
        original_name: str,
        content_type: str | None,
        integration_ok: bool,
    ) -> DocumentViewerHandlerId:
        try:
            return resolve_viewer_handler_id(
                file_category=file_category,
                onlyoffice_eligible=supports_onlyoffice_viewer(original_name, content_type),
                integration_configured=integration_ok,
            )
        except ValueError as exc:
            if str(exc) == "office_integration_not_configured":
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def _handler(self, handler_id: DocumentViewerHandlerId):
        handler = self._handlers.get(handler_id)
        if handler is None:
            raise HTTPException(status_code=500, detail=f"Handler {handler_id} не зарегистрирован")
        return handler

    def build_context(
        self,
        *,
        request: Request,
        handler_id: DocumentViewerHandlerId,
        binding_id: str,
        binding_kind: str,
        file_record: FileRecord,
        title: str,
        file_category: str,
        onlyoffice_document_type: str | None,
        namespace: str | None,
        company_id: str,
        user_id: str,
        user_name: str,
        editor_lang: str,
        link_permission: OfficeViewerLinkPermission = "edit",
        public_link_token_hash: str | None = None,
    ) -> ViewerOpenContext:
        settings = get_office_settings()
        integ = settings.office
        return ViewerOpenContext(
            handler_id=handler_id,
            binding_id=binding_id,
            binding_kind=binding_kind,
            file_record=file_record,
            title=title,
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            namespace=namespace,
            company_id=company_id,
            user_id=user_id,
            user_name=user_name,
            editor_lang=editor_lang,
            callback_public_base_url=integ.callback_public_base_url,
            document_server_public_url=integ.document_server_public_url,
            jwt_secret=integ.jwt_secret,
            download_token_ttl_seconds=integ.download_token_ttl_seconds,
            browser_public_base_url=browser_public_base_url(request),
            browser_document_server_url=browser_document_server_url(
                integ.document_server_public_url,
                request,
            ),
            link_permission="edit" if link_permission == "edit" else "view",
            public_link_token_hash=public_link_token_hash,
        )

    async def open_config_for_binding(
        self,
        *,
        request: Request,
        binding: OfficeDocumentBinding,
        file_record: FileRecord,
        user_id: str,
        user_name: str,
        editor_lang: str,
    ) -> DocumentOpenConfigResponse:
        integration_ok, detail = integration_configured()
        file_category = binding.file_category
        handler_id = self.resolve_handler_id(
            file_category=file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        if handler_id == "onlyoffice" and not integration_ok:
            raise HTTPException(status_code=503, detail=detail)
        ctx = self.build_context(
            request=request,
            handler_id=handler_id,
            binding_id=binding.binding_id,
            binding_kind="document",
            file_record=file_record,
            title=binding.title,
            file_category=file_category,
            onlyoffice_document_type=binding.onlyoffice_document_type,
            namespace=binding.namespace,
            company_id=binding.company_id,
            user_id=user_id,
            user_name=user_name,
            editor_lang=editor_lang,
        )
        return await self._handler(handler_id).build_open_config(ctx)

    async def open_config_for_public_link(
        self,
        *,
        request: Request,
        target: PublicLinkTarget,
        file_record: FileRecord,
    ) -> DocumentOpenConfigResponse:
        if target.kind != "binding" or target.binding is None:
            raise HTTPException(status_code=400, detail="Откройте файл по прямой ссылке")
        binding = target.binding
        integration_ok, detail = integration_configured()
        file_category = binding.file_category
        handler_id = self.resolve_handler_id(
            file_category=file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        if handler_id == "onlyoffice" and not integration_ok:
            raise HTTPException(status_code=503, detail=detail)
        resolved_link_permission: OfficeViewerLinkPermission = (
            "edit" if binding.link_permission == "edit" else "view"
        )
        ctx = self.build_context(
            request=request,
            handler_id=handler_id,
            binding_id=binding.binding_id,
            binding_kind="document",
            file_record=file_record,
            title=binding.title,
            file_category=file_category,
            onlyoffice_document_type=binding.onlyoffice_document_type,
            namespace=binding.namespace,
            company_id=binding.company_id,
            user_id="public",
            user_name="Guest",
            editor_lang=Language.EN.value,
            link_permission=resolved_link_permission,
            public_link_token_hash=target.token_hash,
        )
        return await self._handler(handler_id).build_open_config(ctx)

    async def open_config_for_file(
        self,
        *,
        request: Request,
        file_record: FileRecord,
        company_id: str,
        user_id: str,
        user_name: str,
        editor_lang: str,
        file_category: str,
        onlyoffice_document_type: str | None,
    ) -> DocumentOpenConfigResponse:
        integration_ok, detail = integration_configured()
        handler_id = self.resolve_handler_id(
            file_category=file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        if handler_id == "onlyoffice" and not integration_ok:
            raise HTTPException(status_code=503, detail=detail)
        binding_id = file_viewer_binding_id(file_record.file_id)
        ctx = self.build_context(
            request=request,
            handler_id=handler_id,
            binding_id=binding_id,
            binding_kind="file",
            file_record=file_record,
            title=file_record.original_name,
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            namespace=None,
            company_id=company_id,
            user_id=user_id,
            user_name=user_name,
            editor_lang=editor_lang,
        )
        return await self._handler(handler_id).build_open_config(ctx)

    def capabilities_for_file(
        self,
        *,
        file_category: str,
        file_record: FileRecord,
    ) -> DocumentOpenCapabilities:
        integration_ok, _ = integration_configured()
        handler_id = self.resolve_handler_id(
            file_category=file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        return self._handler(handler_id).capabilities(
            file_record=file_record,
            integration_configured=integration_ok,
        )

    async def preview_for_binding(
        self,
        *,
        binding: OfficeDocumentBinding,
        file_record: FileRecord,
    ) -> str | None:
        integration_ok, _ = integration_configured()
        handler_id = self.resolve_handler_id(
            file_category=binding.file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        handler = self._handler(handler_id)
        caps = handler.capabilities(file_record=file_record, integration_configured=integration_ok)
        if not caps.preview:
            return None
        if handler_id == "image":
            return file_record.url
        if handler_id == "text":
            return None
        return None

    def default_editor_lang(self, language: Language | None) -> str:
        if language is None:
            return Language.EN.value
        return language.value
