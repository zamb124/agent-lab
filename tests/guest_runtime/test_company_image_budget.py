from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone

import pytest

from core.guest_runtime.models import (
    GuestBuildStatus,
    GuestInvokeKind,
    GuestLanguage,
    GuestRuntime,
    guest_runtime_id,
)


@pytest.fixture
async def guest_runtime_record_ids(
    guest_runtime_di,
) -> AsyncIterator[list[str]]:
    _ = guest_runtime_di
    ids: list[str] = []
    yield ids
    for runtime_id in ids:
        deleted = await GuestRuntime.delete_by_id(runtime_id)
        _ = deleted


@pytest.mark.asyncio
async def test_company_image_budget_exceeded(
    guest_runtime_di,
    guest_runtime_record_ids: list[str],
    unique_id: str,
) -> None:
    company_id = f"co_guest_budget_{unique_id}"
    flow_id = f"flow_budget_{unique_id}"
    node_id = "agent"
    runtime_id = guest_runtime_id(flow_id, node_id)
    budget = guest_runtime_di.farm_service.farm_config.company_image_budget_bytes
    runtime = GuestRuntime(
        guest_runtime_id=runtime_id,
        flow_id=flow_id,
        node_id=node_id,
        company_id=company_id,
        catalog_id=f"cat_budget_{unique_id}",
        language=GuestLanguage.PYTHON,
        invoke_kind=GuestInvokeKind.CLI,
        invoke_argv=["python", "main.py"],
        image_digest=f"inprocess:old-{unique_id}",
        image_bytes=budget,
        build_status=GuestBuildStatus.READY,
        updated_at=datetime.now(timezone.utc),
    )
    saved = await GuestRuntime.set(runtime)
    assert saved is True
    guest_runtime_record_ids.append(runtime_id)
    with pytest.raises(ValueError, match="company image budget"):
        await guest_runtime_di.farm_service._assert_company_budget(
            company_id,
            1,
            f"inprocess:new-{unique_id}",
        )
