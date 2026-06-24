"""URL helpers для viewer handlers."""

from __future__ import annotations

from urllib.parse import quote

from apps.office.services.onlyoffice_jwt import encode_download_token
from apps.office.services.viewer_context import ViewerOpenContext
from core.documents.viewer.jwt import encode_viewer_stream_token
from core.documents.viewer.models import DocumentViewerHandlerId, OfficeViewerBindingKind


def office_signed_download_url(
    *,
    base_url: str,
    file_id: str,
    company_id: str,
    binding_id: str,
    binding_kind: OfficeViewerBindingKind,
    secret: str,
    ttl_seconds: int,
) -> str:
    download_token = encode_download_token(
        file_id=file_id,
        company_id=company_id,
        binding_id=binding_id,
        binding_kind=binding_kind,
        secret=secret,
        ttl_seconds=ttl_seconds,
    )
    return f"{base_url.rstrip('/')}/documents/api/v1/office-download?token={quote(download_token, safe='')}"


def download_url_for_context(ctx: ViewerOpenContext) -> str | None:
    binding_kind: OfficeViewerBindingKind = "file" if ctx.binding_kind == "file" else "document"
    return office_signed_download_url(
        base_url=ctx.callback_public_base_url,
        file_id=ctx.file_record.file_id,
        company_id=ctx.company_id,
        binding_id=ctx.binding_id,
        binding_kind=binding_kind,
        secret=ctx.jwt_secret,
        ttl_seconds=ctx.download_token_ttl_seconds,
    )


def viewer_stream_url(
    *,
    base_url: str,
    handler: DocumentViewerHandlerId,
    binding_kind: OfficeViewerBindingKind,
    binding_id: str,
    file_id: str,
    company_id: str,
    content_type: str,
    secret: str,
    ttl_seconds: int,
    edit_mode: bool = False,
    public_link_token_hash: str | None = None,
) -> str:
    token = encode_viewer_stream_token(
        handler=handler,
        binding_kind=binding_kind,
        binding_id=binding_id,
        file_id=file_id,
        company_id=company_id,
        content_type=content_type,
        secret=secret,
        ttl_seconds=ttl_seconds,
        edit_mode=edit_mode,
        public_link_token_hash=public_link_token_hash,
    )
    return f"{base_url.rstrip('/')}/documents/api/v1/viewer-stream?token={quote(token, safe='')}"


def viewer_frame_url(
    *,
    base_url: str,
    handler: DocumentViewerHandlerId,
    binding_kind: OfficeViewerBindingKind,
    binding_id: str,
    file_id: str,
    company_id: str,
    content_type: str,
    secret: str,
    ttl_seconds: int,
    edit_mode: bool = False,
    public_link_token_hash: str | None = None,
) -> str:
    token = encode_viewer_stream_token(
        handler=handler,
        binding_kind=binding_kind,
        binding_id=binding_id,
        file_id=file_id,
        company_id=company_id,
        content_type=content_type,
        secret=secret,
        ttl_seconds=ttl_seconds,
        edit_mode=edit_mode,
        public_link_token_hash=public_link_token_hash,
    )
    return f"{base_url.rstrip('/')}/documents/api/v1/viewer-frame?token={quote(token, safe='')}"


def viewer_save_url(
    *,
    base_url: str,
    binding_kind: OfficeViewerBindingKind,
    binding_id: str,
    file_id: str,
    company_id: str,
    secret: str,
    ttl_seconds: int,
    public_link_token_hash: str | None = None,
) -> str:
    from core.documents.viewer.jwt import encode_viewer_save_token

    token = encode_viewer_save_token(
        binding_kind=binding_kind,
        binding_id=binding_id,
        file_id=file_id,
        company_id=company_id,
        secret=secret,
        ttl_seconds=ttl_seconds,
        public_link_token_hash=public_link_token_hash,
    )
    return f"{base_url.rstrip('/')}/documents/api/v1/viewer-save?token={quote(token, safe='')}"
