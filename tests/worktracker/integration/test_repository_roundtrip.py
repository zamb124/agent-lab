"""WorkItem roundtrip: variables, attachments, correlation, CRM map."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.files.file_ref import FileRef
from core.variables.models import normalize_variables_map
from core.worktracker.models import (
    CrmEntityLink,
    SystemActor,
    WorkItem,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemKind,
    WorkItemState,
)

pytestmark = pytest.mark.asyncio


async def test_repository_save_and_load_work_item(unique_id: str) -> None:
    now = datetime.now(timezone.utc)
    item = WorkItem(
        work_item_id=f"wi_repo_{unique_id}",
        company_id="system",
        title=f"Repo {unique_id}",
        created_by=SystemActor(),
        variables=normalize_variables_map({"k": "v"}),
        attachments=[
            FileRef(
                file_id=f"f_{unique_id}",
                original_name="a.txt",
                content_type="text/plain",
                file_size=1,
            )
        ],
        links=[CrmEntityLink(entity_id=f"ent_{unique_id}")],
        created_at=now,
        updated_at=now,
        state=WorkItemState.OPEN,
    )
    _ = await WorkItem.set(item)
    loaded = await WorkItem.objects.filter(
        company_id="system",
        work_item_id=item.work_item_id,
    ).get_or_none()
    assert loaded is not None
    assert loaded.variables["k"].value == "v"
    assert loaded.attachments[0].file_id == f"f_{unique_id}"
    assert loaded.links[0].entity_id == f"ent_{unique_id}"
    item.title = f"Repo updated {unique_id}"
    updated = await WorkItem.set(item)
    assert updated is True
    reloaded = await WorkItem.get(item.work_item_id)
    assert reloaded is not None
    assert reloaded.title == item.title


async def test_find_by_completion_correlation(unique_id: str) -> None:
    correlation_id = f"corr-{unique_id}"
    now = datetime.now(timezone.utc)
    item = WorkItem(
        work_item_id=f"wi_corr_{unique_id}",
        company_id="system",
        title="HITL",
        kind=WorkItemKind.OPERATOR_HANDOFF,
        created_by=SystemActor(),
        hooks=[
            WorkItemHook(
                event=WorkItemHookEvent.COMPLETED,
                service="flows",
                path="platform:events",
                binding={"correlation_id": correlation_id},
            )
        ],
        created_at=now,
        updated_at=now,
        state=WorkItemState.OPEN,
    )
    _ = await WorkItem.set(item)
    found = await WorkItem.any_by_correlation_id(
        "system",
        correlation_id,
    )
    assert found is not None
    assert found.work_item_id == item.work_item_id


async def test_ids_by_crm_entity_id(unique_id: str) -> None:
    entity_id = f"ent_map_{unique_id}"
    now = datetime.now(timezone.utc)
    item = WorkItem(
        work_item_id=f"wi_crm_{unique_id}",
        company_id="system",
        title="CRM task",
        kind=WorkItemKind.CRM_ACTIVITY,
        created_by=SystemActor(),
        links=[CrmEntityLink(entity_id=entity_id)],
        created_at=now,
        updated_at=now,
        state=WorkItemState.OPEN,
    )
    _ = await WorkItem.set(item)
    mapping = await WorkItem.ids_by_crm_entity_id(
        "system",
        [entity_id],
    )
    assert mapping[entity_id] == item.work_item_id
