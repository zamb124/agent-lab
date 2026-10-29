"""Unit-тесты viewer handler registry и resolver."""

from __future__ import annotations

import pytest

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers._urls import download_url_for_context
from apps.office.services.viewer_handlers.binary_handler import BinaryViewerHandler
from apps.office.services.viewer_handlers.image_handler import ImageViewerHandler
from apps.office.services.viewer_handlers.text_handler import TextViewerHandler
from apps.office.services.viewer_service import DocumentViewerService
from core.documents.viewer.resolver import (
    resolve_file_category_for_upload,
    resolve_viewer_handler_id,
)
from core.documents.viewer.text_presentation import resolve_text_presentation
from core.errors.boundary import PlatformUnavailableError
from core.files.models import FileRecord
from core.files.object_storage import PLATFORM_STORAGE_ID
from core.files.types import FileCategory


def _sample_file_record(**overrides: object) -> FileRecord:
    base = {
        "file_id": "f-json",
        "provider": "seaweedfs",
        "original_name": "package-lock.json",
        "content_type": "application/json",
        "file_size": 1200,
        "checksum": "abc",
        "storage_id": PLATFORM_STORAGE_ID,
        "s3_key": "k",
        "download_url": "/files/download/f-json",
        "company_id": "c1",
        "uploaded_by": "u1",
        "is_public": False,
    }
    base.update(overrides)
    return FileRecord(**base)


def test_download_url_for_context_uses_browser_host_not_callback() -> None:
    file_record = _sample_file_record()
    ctx = ViewerOpenContext(
        handler_id="data_table",
        viewer_scope="file",
        file_record=file_record,
        title="leads",
        file_category=FileCategory.DATA_TABLE.value,
        onlyoffice_document_type=None,
        namespace=None,
        company_id="c1",
        user_id="u1",
        user_name="User",
        editor_lang="ru",
        callback_public_base_url="http://host.docker.internal:8008",
        document_server_public_url="http://localhost:8002",
        jwt_secret="test-onlyoffice-jwt-secret",
        download_token_ttl_seconds=3600,
        browser_public_base_url="http://system.lvh.me:8008",
        browser_document_server_url="http://system.lvh.me:8008",
    )
    download_url = download_url_for_context(ctx)
    assert download_url is not None
    assert "system.lvh.me:8008" in download_url
    assert "host.docker.internal" not in download_url


@pytest.mark.asyncio
async def test_text_handler_urls_use_browser_base_not_docker_internal() -> None:
    file_record = _sample_file_record()
    ctx = ViewerOpenContext(
        handler_id="text",
        viewer_scope="catalog",
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
        jwt_secret="test-onlyoffice-jwt-secret",
        download_token_ttl_seconds=3600,
        browser_public_base_url="http://system.lvh.me:8008",
        browser_document_server_url="http://system.lvh.me:8008",
    )
    config = await TextViewerHandler().build_open_config(ctx)
    assert config.text is not None
    assert "system.lvh.me:8008" in config.text.stream_url
    assert "host.docker.internal" not in config.text.stream_url
    assert config.text.presentation == "code"
    assert config.text.default_view_mode == "source"
    if config.text.save_url:
        assert "system.lvh.me:8008" in config.text.save_url
        assert "host.docker.internal" not in config.text.save_url


@pytest.mark.parametrize(
    ("original_name", "content_type", "presentation", "default_view_mode"),
    [
        ("slide.html", "text/html", "html", "preview"),
        ("index.htm", "text/plain", "html", "preview"),
        ("notes.md", "text/markdown", "markdown", "preview"),
        ("readme.markdown", "text/plain", "markdown", "preview"),
        ("data.json", "application/json", "code", "source"),
        ("script.py", "text/x-python", "code", "source"),
    ],
)
def test_resolve_text_presentation(
    original_name: str,
    content_type: str,
    presentation: str,
    default_view_mode: str,
) -> None:
    resolved_presentation, resolved_mode = resolve_text_presentation(
        original_name=original_name,
        content_type=content_type,
    )
    assert resolved_presentation == presentation
    assert resolved_mode == default_view_mode


@pytest.mark.asyncio
async def test_text_handler_html_presentation_preview_default() -> None:
    file_record = _sample_file_record(
        file_id="f-html",
        original_name="deck.html",
        content_type="text/html",
        file_size=400,
    )
    ctx = ViewerOpenContext(
        handler_id="text",
        viewer_scope="file",
        file_record=file_record,
        title="deck",
        file_category=FileCategory.TEXT.value,
        onlyoffice_document_type=None,
        namespace=None,
        company_id="c1",
        user_id="u1",
        user_name="User",
        editor_lang="ru",
        callback_public_base_url="http://host.docker.internal:8008",
        document_server_public_url="http://localhost:8002",
        jwt_secret="test-onlyoffice-jwt-secret",
        download_token_ttl_seconds=3600,
        browser_public_base_url="http://system.lvh.me:8008",
        browser_document_server_url="http://system.lvh.me:8008",
    )
    config = await TextViewerHandler().build_open_config(ctx)
    assert config.text is not None
    assert config.text.presentation == "html"
    assert config.text.default_view_mode == "preview"


@pytest.mark.asyncio
async def test_text_handler_markdown_presentation_preview_default() -> None:
    file_record = _sample_file_record(
        file_id="f-md",
        original_name="notes.md",
        content_type="text/markdown",
        file_size=400,
    )
    ctx = ViewerOpenContext(
        handler_id="text",
        viewer_scope="file",
        file_record=file_record,
        title="notes",
        file_category=FileCategory.TEXT.value,
        onlyoffice_document_type=None,
        namespace=None,
        company_id="c1",
        user_id="u1",
        user_name="User",
        editor_lang="ru",
        callback_public_base_url="http://host.docker.internal:8008",
        document_server_public_url="http://localhost:8002",
        jwt_secret="test-onlyoffice-jwt-secret",
        download_token_ttl_seconds=3600,
        browser_public_base_url="http://system.lvh.me:8008",
        browser_document_server_url="http://system.lvh.me:8008",
    )
    config = await TextViewerHandler().build_open_config(ctx)
    assert config.text is not None
    assert config.text.presentation == "markdown"
    assert config.text.default_view_mode == "preview"


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


def test_resolve_viewer_handler_viz() -> None:
    handler_id = resolve_viewer_handler_id(
        file_category=FileCategory.VIZ.value,
        onlyoffice_eligible=False,
        integration_configured=True,
    )
    assert handler_id == "viz"


def test_resolve_viewer_handler_data_table() -> None:
    handler_id = resolve_viewer_handler_id(
        file_category=FileCategory.DATA_TABLE.value,
        onlyoffice_eligible=False,
        integration_configured=True,
    )
    assert handler_id == "data_table"


def test_resolve_file_category_data_table() -> None:
    category = resolve_file_category_for_upload(
        "leads.sqlite",
        "application/vnd.sqlite3",
    )
    assert category == FileCategory.DATA_TABLE.value
    db_category = resolve_file_category_for_upload("scratch.db", None)
    assert db_category == FileCategory.DATA_TABLE.value


def test_resolve_file_category_viz() -> None:
    category = resolve_file_category_for_upload(
        "funnel.viz",
        "application/vnd.platform.viz+json",
    )
    assert category == FileCategory.VIZ.value


def test_image_handler_capabilities() -> None:
    file_record = FileRecord(
        file_id="f1",
                original_name="a.png",
        content_type="image/png",
        file_size=100,
        checksum="abc",
        storage_id=PLATFORM_STORAGE_ID,
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
                original_name="big.txt",
        content_type="text/plain",
        file_size=900_000,
        checksum="abc",
        storage_id=PLATFORM_STORAGE_ID,
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
                original_name="archive.zip",
        content_type="application/zip",
        file_size=10,
        checksum="abc",
        storage_id=PLATFORM_STORAGE_ID,
        s3_key="k",
        download_url="/files/download/f3",
        company_id="c1",
        uploaded_by="u1",
        is_public=False,
    )
    caps = BinaryViewerHandler().capabilities(file_record=file_record, integration_configured=True)
    assert caps.preview is False


def test_viewer_service_resolve_handler_id_unavailable_on_missing_integration() -> None:
    service = DocumentViewerService()
    with pytest.raises(PlatformUnavailableError, match="office_integration_not_configured"):
        service.resolve_handler_id(
            file_category=FileCategory.OFFICE_DOC.value,
            original_name="doc.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            integration_ok=False,
        )
