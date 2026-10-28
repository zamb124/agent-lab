"""Ревизии документа."""

from __future__ import annotations

import pytest

from apps.office.models.revision import OfficeDocumentRevision


@pytest.mark.asyncio
async def test_append_numbers_revisions_for_one_file(
    office_di,
    unique_id: str,
) -> None:
    _ = office_di
    file_id = f"file-{unique_id}"
    first = await OfficeDocumentRevision.append(
        file_id=file_id,
        revision_file_id=f"snap-1-{unique_id}",
        created_by_user_id="user-1",
    )
    second = await OfficeDocumentRevision.append(
        file_id=file_id,
        revision_file_id=f"snap-2-{unique_id}",
        created_by_user_id="user-1",
    )
    assert first.revision_number == 1
    assert second.revision_number == 2
    listed = await OfficeDocumentRevision.list_by_revision_number_desc(file_id, limit=10)
    assert [row.revision_number for row in listed] == [2, 1]
