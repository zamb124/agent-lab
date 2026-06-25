"""Repository roundtrip: variables, attachments, correlation, CRM map."""

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


async def test_repository_save_and_load_work_item(
    worktracker_repository,
    unique_id: str,
) -> None:
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
    saved = await worktracker_repository.save_work_item(item)
    loaded = await worktracker_repository.get_work_item("system", saved.work_item_id)
    assert loaded.variables["k"].value == "v"
    assert loaded.attachments[0].file_id == f"f_{unique_id}"
    assert loaded.links[0].entity_id == f"ent_{unique_id}"


async def test_find_by_completion_correlation(
    worktracker_repository,
    unique_id: str,
) -> None:
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
                path="/flows/api/v1/internal/work-items/completed",
                binding={"correlation_id": correlation_id},
            )
        ],
        created_at=now,
        updated_at=now,
        state=WorkItemState.OPEN,
    )
    saved = await worktracker_repository.save_work_item(item)
    found = await worktracker_repository.find_work_item_by_correlation(
        "system",
        correlation_id,
    )
    assert found is not None
    assert found.work_item_id == saved.work_item_id


async def test_map_work_item_ids_by_crm_entities(
    worktracker_repository,
    unique_id: str,
) -> None:
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
    saved = await worktracker_repository.save_work_item(item)
    mapping = await worktracker_repository.map_work_item_ids_by_crm_entities(
        "system",
        [entity_id],
    )
    assert mapping[entity_id] == saved.work_item_id
