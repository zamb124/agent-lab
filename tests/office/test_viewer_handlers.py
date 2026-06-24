"""Unit-тесты viewer handler registry и resolver."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers.binary_handler import BinaryViewerHandler
from apps.office.services.viewer_handlers.image_handler import ImageViewerHandler
from apps.office.services.viewer_handlers.text_handler import TextViewerHandler
from apps.office.services.viewer_service import DocumentViewerService, browser_public_base_url
from core.documents.viewer.resolver import (
    resolve_file_category_for_upload,
    resolve_viewer_handler_id,
)
from core.files.models import FileRecord
from core.files.types import FileCategory


def _request(
    *,
    scheme: str = "http",
    server: tuple[str, int] = ("system.lvh.me", 8008),
    headers: Mapping[str, str] | None = None,
) -> Request:
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    if not any(key == b"host" for key, _ in raw_headers):
        host = server[0] if server[1] in (80, 443) else f"{server[0]}:{server[1]}"
        raw_headers.append((b"host", host.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": scheme,
            "server": server,
            "path": "/documents/api/v1/documents/b1/editor-config",
            "headers": raw_headers,
        }
    )


def _sample_file_record(**overrides: object) -> FileRecord:
    base = {
        "file_id": "f-json",
        "provider": "minio",
        "original_name": "package-lock.json",
        "content_type": "application/json",
        "file_size": 1200,
        "checksum": "abc",
        "s3_bucket": "b",
        "s3_key": "k",
        "download_url": "/files/download/f-json",
        "company_id": "c1",
        "uploaded_by": "u1",
        "is_public": False,
    }
    base.update(overrides)
    return FileRecord(**base)


def test_browser_public_base_url_uses_request_host() -> None:
    request = _request()
    assert browser_public_base_url(request) == "http://system.lvh.me:8008"


@pytest.mark.asyncio
async def test_text_handler_urls_use_browser_base_not_docker_internal() -> None:
    request = _request()
    file_record = _sample_file_record()
    ctx = ViewerOpenContext(
        handler_id="text",
        binding_id="b1",
        binding_kind="document",
        file_record=file_record,
        title="package-lock",
        file_category=FileCategory.TEXT.value,
        onlyoffice_document_type=None,
        namespace=None,
        company_id="c1",
        user_id="u1",
        user_name="User",
        editor_lang="ru",
        callback_public_base_url="http://host.docker.internal:8008",
        document_server_public_url="http://localhost:8002",
        jwt_secret="test-secret",
        download_token_ttl_seconds=3600,
        browser_public_base_url=browser_public_base_url(request),
        browser_document_server_url="http://system.lvh.me:8008",
    )
    config = await TextViewerHandler().build_open_config(ctx)
    assert config.text is not None
    assert "system.lvh.me:8008" in config.text.stream_url
    assert "host.docker.internal" not in config.text.stream_url
    if config.text.save_url:
        assert "system.lvh.me:8008" in config.text.save_url
        assert "host.docker.internal" not in config.text.save_url


def test_resolve_file_category_png() -> None:
    category = resolve_file_category_for_upload("photo.png", "image/png")
    assert category == FileCategory.IMAGE.value


def test_resolve_viewer_handler_onlyoffice_requires_integration() -> None:
    with pytest.raises(ValueError, match="office_integration_not_configured"):
        resolve_viewer_handler_id(
            file_category=FileCategory.OFFICE_DOC.value,
            onlyoffice_eligible=True,
            integration_configured=False,
        )


def test_resolve_viewer_handler_image() -> None:
    handler_id = resolve_viewer_handler_id(
        file_category=FileCategory.IMAGE.value,
        onlyoffice_eligible=False,
        integration_configured=True,
    )
    assert handler_id == "image"


def test_resolve_viewer_handler_binary_unknown() -> None:
    handler_id = resolve_viewer_handler_id(
        file_category="unknown",
        onlyoffice_eligible=False,
        integration_configured=True,
    )
    assert handler_id == "binary"


def test_image_handler_capabilities() -> None:
    file_record = FileRecord(
        file_id="f1",
        provider="minio",
        original_name="a.png",
        content_type="image/png",
        file_size=100,
        checksum="abc",
        s3_bucket="b",
        s3_key="k",
        download_url="/files/download/f1",
        company_id="c1",
        uploaded_by="u1",
        is_public=False,
    )
    caps = ImageViewerHandler().capabilities(file_record=file_record, integration_configured=True)
    assert caps.view is True
    assert caps.edit is False
    assert caps.server_mutations is False


def test_text_handler_edit_disabled_for_large_file() -> None:
    file_record = FileRecord(
        file_id="f2",
        provider="minio",
        original_name="big.txt",
        content_type="text/plain",
        file_size=900_000,
        checksum="abc",
        s3_bucket="b",
        s3_key="k",
        download_url="/files/download/f2",
        company_id="c1",
        uploaded_by="u1",
        is_public=False,
    )
    caps = TextViewerHandler().capabilities(file_record=file_record, integration_configured=True)
    assert caps.view is True
    assert caps.edit is False


def test_binary_handler_capabilities() -> None:
    file_record = FileRecord(
        file_id="f3",
        provider="minio",
        original_name="archive.zip",
        content_type="application/zip",
        file_size=10,
        checksum="abc",
        s3_bucket="b",
        s3_key="k",
        download_url="/files/download/f3",
        company_id="c1",
        uploaded_by="u1",
        is_public=False,
    )
    caps = BinaryViewerHandler().capabilities(file_record=file_record, integration_configured=True)
    assert caps.preview is False


def test_viewer_service_resolve_handler_id_http_on_missing_integration() -> None:
    service = DocumentViewerService()
    with pytest.raises(HTTPException) as exc_info:
        service.resolve_handler_id(
            file_category=FileCategory.OFFICE_DOC.value,
            original_name="doc.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            integration_ok=False,
        )
    assert exc_info.value.status_code == 503
