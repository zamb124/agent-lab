"""Orchestration viewer handlers для office BFF."""

from __future__ import annotations

from urllib.parse import urlparse

from apps.office.config import get_office_settings
from apps.office.models.link import DocumentLink
from apps.office.services.document_lifecycle import document_title
from apps.office.services.document_type import supports_onlyoffice_viewer
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from apps.office.services.office_access_service import PublicLinkTarget
from apps.office.services.viewer_context import OfficeViewerLinkPermission, ViewerOpenContext
from apps.office.services.viewer_handlers.binary_handler import BinaryViewerHandler
from apps.office.services.viewer_handlers.data_table_handler import DataTableViewerHandler
from apps.office.services.viewer_handlers.image_handler import ImageViewerHandler
from apps.office.services.viewer_handlers.media_handler import MediaViewerHandler
from apps.office.services.viewer_handlers.onlyoffice_handler import OnlyOfficeViewerHandler
from apps.office.services.viewer_handlers.text_handler import TextViewerHandler
from apps.office.services.viewer_handlers.viz_handler import VizViewerHandler
from core.documents.catalog import DocumentCatalog
from core.documents.viewer.models import (
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
    OfficeViewerScope,
)
from core.documents.viewer.resolver import resolve_viewer_handler_id
from core.errors.boundary import PlatformUnavailableError
from core.files.models import FileRecord
from core.models.i18n_models import Language
from core.platform_brand.resolver import resolve_infrastructure_service_url

_LOCAL_DOCUMENT_SERVER_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_OfficeViewerHandler = (
    OnlyOfficeViewerHandler
    | ImageViewerHandler
    | MediaViewerHandler
    | TextViewerHandler
    | BinaryViewerHandler
    | VizViewerHandler
    | DataTableViewerHandler
)


def integration_configured() -> tuple[bool, str]:
    settings = get_office_settings().office
    if not settings.jwt_secret.strip():
        return False, "Не задан office.jwt_secret (совпадает с JWT_SECRET Document Server)"
    if not settings.document_server_public_url.strip():
        return False, "Не задан office.document_server_public_url"
    if not settings.callback_public_base_url.strip():
        return False, "Не задан office.callback_public_base_url (доступен с контейнера Document Server)"
    return True, ""


def browser_document_server_url(raw_url: str, public_origin: str) -> str:
    """URL Document Server для браузера пользователя.

    Локальный `document_server_public_url` (dev) проксируется через тот же origin,
    что и SPA; иначе адрес берётся из карты инфраструктуры бренда по host'у origin'а.
    """
    value = raw_url.strip().rstrip("/")
    if not value:
        raise ValueError("document_server_public_url is empty")
    origin = urlparse(public_origin)
    if origin.scheme not in ("http", "https") or not origin.netloc:
        raise ValueError(f"public_origin must be http(s)://host[:port], got {public_origin!r}")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host in _LOCAL_DOCUMENT_SERVER_HOSTS:
        return f"{origin.scheme}://{origin.netloc}"
    resolved = resolve_infrastructure_service_url(origin.netloc, "onlyoffice")
    return urlparse(resolved)._replace(scheme=origin.scheme).geturl().rstrip("/")


class DocumentViewerService:
    def __init__(self) -> None:
        self._handlers: dict[DocumentViewerHandlerId, _OfficeViewerHandler] = {
            "onlyoffice": OnlyOfficeViewerHandler(),
            "image": ImageViewerHandler(),
            "media": MediaViewerHandler(),
            "text": TextViewerHandler(),
            "binary": BinaryViewerHandler(),
            "viz": VizViewerHandler(),
            "data_table": DataTableViewerHandler(),
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
                raise PlatformUnavailableError(str(exc)) from exc
            raise

    def _handler(self, handler_id: DocumentViewerHandlerId) -> _OfficeViewerHandler:
        handler = self._handlers.get(handler_id)
        if handler is None:
            raise RuntimeError(f"Handler {handler_id} is not registered")
        return handler

    def build_context(
        self,
        *,
        public_origin: str,
        handler_id: DocumentViewerHandlerId,
        viewer_scope: OfficeViewerScope,
        file_record: FileRecord,
        title: str,
        file_category: str,
        onlyoffice_document_type: str | None,
        namespace: str | None,
        company_id: str,
        user_id: str,
        user_name: str,
        editor_lang: str,
        link_permission: OfficeViewerLinkPermission = "editor",
        public_link_token_hash: str | None = None,
    ) -> ViewerOpenContext:
        settings = get_office_settings()
        integ = settings.office
        return ViewerOpenContext(
            handler_id=handler_id,
            viewer_scope=viewer_scope,
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
            browser_public_base_url=public_origin,
            browser_document_server_url=browser_document_server_url(
                integ.document_server_public_url,
                public_origin,
            ),
            link_permission=link_permission,
            public_link_token_hash=public_link_token_hash,
        )

    async def open_config_for_binding(
        self,
        *,
        public_origin: str,
        binding: FileRecord,
        file_record: FileRecord,
        user_id: str,
        user_name: str,
        editor_lang: str,
    ) -> DocumentOpenConfigResponse:
        integration_ok, detail = integration_configured()
        file_category, onlyoffice_document_type = resolve_binding_metadata(
            binding.original_name,
            binding.content_type.split(";", 1)[0].strip(),
        )
        catalog = await DocumentCatalog.get(binding.catalog_id or "")
        namespace = catalog.namespace if catalog is not None else ""
        handler_id = self.resolve_handler_id(
            file_category=file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        if handler_id == "onlyoffice" and not integration_ok:
            raise PlatformUnavailableError(detail)
        ctx = self.build_context(
            public_origin=public_origin,
            handler_id=handler_id,
            viewer_scope="catalog",
            file_record=file_record,
            title=document_title(binding),
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            namespace=namespace,
            company_id=binding.company_id or "",
            user_id=user_id,
            user_name=user_name,
            editor_lang=editor_lang,
        )
        return await self._handler(handler_id).build_open_config(ctx)

    async def open_config_for_public_link(
        self,
        *,
        public_origin: str,
        target: PublicLinkTarget,
        file_record: FileRecord,
    ) -> DocumentOpenConfigResponse:
        if target.kind != "binding" or target.binding is None:
            raise ValueError("Open the file via a direct link")
        binding = target.binding
        integration_ok, detail = integration_configured()
        file_category, onlyoffice_document_type = resolve_binding_metadata(
            binding.original_name,
            binding.content_type.split(";", 1)[0].strip(),
        )
        catalog = await DocumentCatalog.get(binding.catalog_id or "")
        namespace = catalog.namespace if catalog is not None else ""
        link = await DocumentLink.for_target("file", binding.file_id)
        link_permission = link.permission if link is not None else "viewer"
        handler_id = self.resolve_handler_id(
            file_category=file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        if handler_id == "onlyoffice" and not integration_ok:
            raise PlatformUnavailableError(detail)
        if link_permission not in ("viewer", "editor"):
            raise ValueError(f"Invalid link_permission: {link_permission}")
        resolved_link_permission: OfficeViewerLinkPermission = link_permission
        ctx = self.build_context(
            public_origin=public_origin,
            handler_id=handler_id,
            viewer_scope="catalog",
            file_record=file_record,
            title=document_title(binding),
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            namespace=namespace,
            company_id=binding.company_id or "",
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
        public_origin: str,
        file_record: FileRecord,
        company_id: str,
        user_id: str,
        user_name: str,
        editor_lang: str,
        file_category: str,
        onlyoffice_document_type: str | None,
        namespace: str | None = None,
    ) -> DocumentOpenConfigResponse:
        integration_ok, detail = integration_configured()
        handler_id = self.resolve_handler_id(
            file_category=file_category,
            original_name=file_record.original_name,
            content_type=file_record.content_type,
            integration_ok=integration_ok,
        )
        if handler_id == "onlyoffice" and not integration_ok:
            raise PlatformUnavailableError(detail)
        ctx = self.build_context(
            public_origin=public_origin,
            handler_id=handler_id,
            viewer_scope="file",
            file_record=file_record,
            title=file_record.original_name,
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            namespace=namespace,
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
        binding: FileRecord,
        file_record: FileRecord,
    ) -> str | None:
        integration_ok, _ = integration_configured()
        file_category, _office_type = resolve_binding_metadata(
            binding.original_name,
            binding.content_type.split(";", 1)[0].strip(),
        )
        handler_id = self.resolve_handler_id(
            file_category=file_category,
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
