"""HITL resume идёт через PlatformEventConsumerService (шина), не HTTP wake."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.flows.src.services.platform_event_consumer import PlatformEventConsumerService
from core.events import EventDelivery, PlatformEvent
from core.types import JsonObject
from core.worktracker.events import WORK_ITEM_COMPLETED
from core.worktracker.models import (
    QueueAssignment,
    SystemActor,
    WorkItem,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemKind,
    WorkItemPriority,
    WorkItemResolution,
    WorkItemState,
)


@pytest.mark.asyncio
async def test_work_item_completed_routes_to_hitl_resume() -> None:
    resume = AsyncMock()
    hitl_service = SimpleNamespace(resume_from_completion=resume)
    container = SimpleNamespace(hitl_work_item_service=hitl_service)
    employee_inbox = SimpleNamespace()
    service = PlatformEventConsumerService(
        container=container,  # type: ignore[arg-type]
        employee_inbox_service=employee_inbox,  # type: ignore[arg-type]
    )

    binding: JsonObject = {
        "session_id": "flow:ctx",
        "flow_id": "flow_1",
        "branch_id": "default",
        "end_user_id": "user_1",
        "context_data_snapshot": {"channel": "a2a"},
    }
    now = datetime.now(timezone.utc)
    item = WorkItem(
        work_item_id="wi_1",
        company_id="company_1",
        title="HITL",
        description="",
        kind=WorkItemKind.OPERATOR_HANDOFF,
        state=WorkItemState.DONE,
        priority=WorkItemPriority.NORMAL,
        created_by=SystemActor(),
        assignment=QueueAssignment(work_queue_id="q1", claimed_by_user_id="u1"),
        blocking=True,
        hooks=[
            WorkItemHook(
                event=WorkItemHookEvent.COMPLETED,
                service="flows",
                path="platform:events",
                binding=binding,
            )
        ],
        resolution=WorkItemResolution(text="ok"),
        created_at=now,
        updated_at=now,
    )
    event = PlatformEvent(
        type=WORK_ITEM_COMPLETED,
        company_id="company_1",
        payload={"work_item": item.model_dump(mode="json")},
        delivery=EventDelivery(company_id="company_1"),
    )

    await service._route_work_item_completed(event)

    resume.assert_awaited_once()
    kwargs = resume.await_args.kwargs
    assert kwargs["work_item_id"] == "wi_1"
    assert kwargs["binding"] == binding
    assert kwargs["company_id"] == "company_1"
    assert isinstance(kwargs["resolution"], WorkItemResolution)
    assert kwargs["resolution"].text == "ok"
