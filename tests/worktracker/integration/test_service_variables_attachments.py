"""WorkItemService: variables и attachments roundtrip через репозиторий."""

from __future__ import annotations

import pytest

from core.files.file_ref import FileRef
from core.variables.models import normalize_variables_map
from core.worktracker.models import SystemActor, WorkItemResolution

pytestmark = pytest.mark.asyncio


async def test_variables_attachments_persist_via_repository(
    worktracker_service,
    worktracker_repository,
    unique_id: str,
) -> None:
    file_ref = FileRef(
        file_id=f"file_{unique_id}",
        original_name="spec.pdf",
        content_type="application/pdf",
        file_size=42,
    )
    variables = normalize_variables_map(
        {"customer": "ACME", "tier": {"value": "gold", "secret": False}}
    )
    item = await worktracker_service.create(
        company_id="system",
        title=f"vars-{unique_id}",
        created_by=SystemActor(),
        variables=variables,
        attachments=[file_ref],
    )

    row_item = await worktracker_repository.get_work_item("system", item.work_item_id)
    assert row_item.attachments[0].file_id == file_ref.file_id
    assert row_item.variables["customer"].value == "ACME"

    await worktracker_service.update(
        company_id="system",
        work_item_id=item.work_item_id,
        variables=normalize_variables_map({"customer": "Beta"}),
    )
    updated_row = await worktracker_repository.get_work_item("system", item.work_item_id)
    assert updated_row.variables["customer"].value == "Beta"


async def test_resolution_files_persist(
    worktracker_service,
    worktracker_repository,
    unique_id: str,
) -> None:
    file_ref = FileRef(
        file_id=f"res_{unique_id}",
        original_name="out.pdf",
        content_type="application/pdf",
        file_size=10,
    )
    item = await worktracker_service.create(
        company_id="system",
        title=f"res-{unique_id}",
        created_by=SystemActor(),
    )
    completion = await worktracker_service.complete(
        company_id="system",
        work_item_id=item.work_item_id,
        resolution=WorkItemResolution(text="done", files=[file_ref]),
    )
    assert completion.work_item.resolution is not None
    assert completion.work_item.resolution.files[0].file_id == file_ref.file_id

    from_db = await worktracker_repository.get_work_item("system", item.work_item_id)
    assert from_db.resolution is not None
    assert from_db.resolution.files[0].file_id == file_ref.file_id
