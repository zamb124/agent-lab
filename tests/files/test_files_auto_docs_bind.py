"""Создание durable-файла само кладёт его в дерево каталогов."""

from __future__ import annotations

import pytest

from core.authz.factory import build_authz_service
from core.config import get_settings
from core.documents.catalog import DocumentCatalog
from core.documents.tree_service import DocumentTreeService
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from tests.fixtures.s3 import require_s3_configured


def _service() -> FilesService:
    return FilesService(
        files_route_segment="frontend",
        tree=DocumentTreeService(build_authz_service(get_settings().openfga)),
    )


@pytest.mark.asyncio
async def test_create_durable_source_creates_catalog_chain(app, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    channel_id = f"ch-{unique_id}"
    record = await _service().create(
        FileCreateSpec(
            source_kind=FileSourceKind.SYNC_MESSAGE,
            source_ref=FileSourceRef(channel_id=channel_id),
            retention=default_retention_for_source(FileSourceKind.SYNC_MESSAGE),
        ),
        f"auto-bind-{unique_id}".encode("utf-8"),
        original_name=f"auto-{unique_id}.txt",
        content_type="text/plain",
    )
    assert record.catalog_id is not None
    catalog = await DocumentCatalog.get(record.catalog_id)
    assert catalog is not None
    assert catalog.title == channel_id
    assert catalog.parent_catalog_id is not None
    parent = await DocumentCatalog.get(catalog.parent_catalog_id)
    assert parent is not None
    assert parent.title == "Sync"
    assert parent.parent_catalog_id is None


@pytest.mark.asyncio
async def test_create_exempt_source_has_no_catalog(app, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    record = await _service().create(
        FileCreateSpec(
            source_kind=FileSourceKind.PLATFORM_AUXILIARY,
            source_ref=FileSourceRef(),
            retention=default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        ),
        f"exempt-{unique_id}".encode("utf-8"),
        original_name=f"exempt-{unique_id}.txt",
        content_type="text/plain",
    )
    assert record.catalog_id is None
    assert record.source_kind == FileSourceKind.PLATFORM_AUXILIARY.value
