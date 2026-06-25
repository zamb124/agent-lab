"""WorkItemService: комментарии и list_comments."""

from __future__ import annotations

import pytest

from core.files.file_ref import FileRef
from core.worktracker.models import SystemActor, UserActor, WorkItemCommentRole

pytestmark = pytest.mark.asyncio


async def test_add_comment_and_list_ordered(worktracker_service, unique_id: str) -> None:
    user_id = f"user_{unique_id}"
    item = await worktracker_service.create_manual_task(
        company_id="system",
        title=f"cmt-{unique_id}",
        created_by=UserActor(user_id=user_id),
    )
    first = await worktracker_service.add_comment(
        company_id="system",
        work_item_id=item.work_item_id,
        author=UserActor(user_id="op1"),
        role=WorkItemCommentRole.OPERATOR,
        text="first",
    )
    second = await worktracker_service.add_comment(
        company_id="system",
        work_item_id=item.work_item_id,
        author=SystemActor(),
        role=WorkItemCommentRole.SYSTEM,
        text="second",
    )
    comments = await worktracker_service.list_comments("system", item.work_item_id)
    assert len(comments) >= 2
    assert comments[0].comment_id == first.comment_id
    assert comments[1].comment_id == second.comment_id


async def test_comment_with_files_roundtrip(worktracker_service, unique_id: str) -> None:
    file_ref = FileRef(
        file_id=f"file_{unique_id}",
        original_name="note.pdf",
        content_type="application/pdf",
        file_size=100,
    )
    item = await worktracker_service.create(
        company_id="system",
        title=f"files-cmt-{unique_id}",
        created_by=SystemActor(),
    )
    saved = await worktracker_service.add_comment(
        company_id="system",
        work_item_id=item.work_item_id,
        author=SystemActor(),
        text="see attachment",
        files=[file_ref],
    )
    assert saved.files[0].file_id == file_ref.file_id
    listed = await worktracker_service.list_comments("system", item.work_item_id)
    assert listed[-1].files[0].original_name == "note.pdf"
