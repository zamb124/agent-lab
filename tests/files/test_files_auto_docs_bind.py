"""FilesService auto DocsPlacement on durable create."""

from __future__ import annotations

import pytest

from core.clients.service_client import ServiceClientError
from core.documents.placement import DocsBindResult, DocsPlacement
from core.files.create_spec import FileCreateSpec, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.files.service import FilesService
from tests.fixtures.s3 import require_s3_configured


@pytest.mark.asyncio
async def test_create_durable_source_auto_binds(app, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    from apps.frontend.container import get_frontend_container

    binds: list[DocsPlacement] = []

    async def recording_bind(placement: DocsPlacement) -> DocsBindResult:
        binds.append(placement)
        return DocsBindResult(
            file_id=placement.file_id,
            catalog_id="cat-auto",
            created=True,
            catalog_path=["Sync", "ch-auto"],
        )

    container = get_frontend_container()
    service = FilesService(
        file_repository=container.file_repository,
        docs_bind_hook=recording_bind,
    )

    record = await service.create(
        FileCreateSpec(
            source_kind=FileSourceKind.SYNC_MESSAGE,
            source_ref=FileSourceRef(channel_id=f"ch-{unique_id}"),
            retention=default_retention_for_source(FileSourceKind.SYNC_MESSAGE),
        ),
        f"auto-bind-{unique_id}".encode("utf-8"),
        original_name=f"auto-{unique_id}.txt",
        content_type="text/plain",
    )
    assert len(binds) == 1
    assert binds[0].file_id == record.file_id
    assert binds[0].anchor is not None
    assert binds[0].anchor.channel_id == f"ch-{unique_id}"


@pytest.mark.asyncio
async def test_create_durable_source_soft_fails_office_bind(app, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    from apps.frontend.container import get_frontend_container

    async def failing_bind(placement: DocsPlacement) -> DocsBindResult:
        _ = placement
        raise ServiceClientError("office unavailable")

    container = get_frontend_container()
    service = FilesService(
        file_repository=container.file_repository,
        docs_bind_hook=failing_bind,
    )

    record = await service.create(
        FileCreateSpec(
            source_kind=FileSourceKind.MAIL_MESSAGE,
            source_ref=FileSourceRef(
                mailbox_binding_id=f"mb-{unique_id}",
                mail_uid=f"uid-{unique_id}",
                mailbox_email=f"user.{unique_id}@example.com",
            ),
            retention=default_retention_for_source(FileSourceKind.MAIL_MESSAGE),
        ),
        f"mail-bind-soft-{unique_id}".encode("utf-8"),
        original_name=f"mail-{unique_id}.txt",
        content_type="text/plain",
    )
    assert record.file_id
    loaded = await service.get(record.file_id)
    assert loaded.file_id == record.file_id


@pytest.mark.asyncio
async def test_create_exempt_source_skips_bind(app, unique_id: str) -> None:
    _ = app
    require_s3_configured()
    from apps.frontend.container import get_frontend_container

    binds: list[DocsPlacement] = []

    async def recording_bind(placement: DocsPlacement) -> DocsBindResult:
        binds.append(placement)
        return DocsBindResult(
            file_id=placement.file_id,
            catalog_id="cat",
            created=True,
            catalog_path=[],
        )

    container = get_frontend_container()
    service = FilesService(
        file_repository=container.file_repository,
        docs_bind_hook=recording_bind,
    )
    _ = await service.create(
        FileCreateSpec(
            source_kind=FileSourceKind.PLATFORM_AUXILIARY,
            source_ref=FileSourceRef(),
            retention=default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        ),
        f"exempt-{unique_id}".encode("utf-8"),
        original_name=f"exempt-{unique_id}.txt",
        content_type="text/plain",
    )
    assert binds == []
