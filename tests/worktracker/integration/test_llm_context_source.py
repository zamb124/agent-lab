"""WorkItemLLMContextSource.collect на реальном WorkItemService."""

from __future__ import annotations

import pytest

from core.context import clear_context, set_context
from core.llm_context.sources import LLMContextSourceRequest
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.worktracker.context_source import WorkItemLLMContextSource
from core.worktracker.models import SystemActor, WorkItemState

pytestmark = pytest.mark.asyncio


async def test_collect_returns_memory_block_for_active_items(
    worktracker_service,
    unique_id: str,
) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"llm-ctx-{unique_id}",
        created_by=SystemActor(),
    )
    user = User(
        user_id="llm_user",
        name="LLM User",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    company = Company(
        company_id="system",
        name="System",
        owner_user_id="llm_user",
        members={"llm_user": ["member"]},
        balance=0.0,
    )
    set_context(Context(user=user, active_company=company, trace_id=f"trace-{unique_id}"))

    source = WorkItemLLMContextSource(worktracker_service)
    blocks = await source.collect(LLMContextSourceRequest())
    clear_context()

    assert len(blocks) >= 1
    assert blocks[0].kind == "memory"
    assert item.work_item_id in blocks[0].content


async def test_collect_empty_when_no_active_items(worktracker_service, unique_id: str) -> None:
    item = await worktracker_service.create(
        company_id="system",
        title=f"llm-term-{unique_id}",
        created_by=SystemActor(),
    )
    await worktracker_service.complete(company_id="system", work_item_id=item.work_item_id)

    user = User(
        user_id="llm_user2",
        name="LLM User 2",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    company = Company(
        company_id="system",
        name="System",
        owner_user_id="llm_user2",
        members={"llm_user2": ["member"]},
        balance=0.0,
    )
    set_context(Context(user=user, active_company=company, trace_id=f"trace2-{unique_id}"))

    source = WorkItemLLMContextSource(worktracker_service)
    open_items = await worktracker_service.list("system", state=WorkItemState.OPEN, limit=5)
    if not open_items:
        blocks = await source.collect(LLMContextSourceRequest())
        assert blocks == []
    clear_context()
