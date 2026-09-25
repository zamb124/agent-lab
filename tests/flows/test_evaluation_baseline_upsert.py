"""Закрепление прогона ветки evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.models.evaluation_lab import EvaluationBaseline


@pytest.mark.asyncio
async def test_upsert_by_suite_and_branch_keeps_baseline_id(di: FlowsDi, unique_id: str) -> None:
    _ = di
    now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    suite_id = f"suite-{unique_id}"
    branch_id = f"branch-{unique_id}"
    created = await EvaluationBaseline.upsert_by_suite_and_branch(
        EvaluationBaseline(
            baseline_id=f"base-{unique_id}",
            suite_id=suite_id,
            flow_id=f"flow-{unique_id}",
            branch_id=branch_id,
            run_id=f"run-{unique_id}",
            created_by="test_user",
            created_at=now,
            updated_at=now,
            company_id="system",
        )
    )
    updated = await EvaluationBaseline.upsert_by_suite_and_branch(
        created.model_copy(
            update={
                "baseline_id": f"other-{unique_id}",
                "run_id": f"run2-{unique_id}",
                "flow_id": f"flow2-{unique_id}",
                "updated_at": datetime(2026, 9, 24, 13, 0, tzinfo=UTC),
            }
        )
    )
    assert updated.baseline_id == created.baseline_id
    assert updated.created_at == created.created_at
    assert updated.run_id == f"run2-{unique_id}"
    assert updated.flow_id == f"flow2-{unique_id}"
    assert await EvaluationBaseline.for_branch(suite_id, f"missing-{unique_id}") is None
    with pytest.raises(ValueError, match="suite_id and branch_id are required"):
        _ = await EvaluationBaseline.upsert_by_suite_and_branch(
            created.model_copy(update={"suite_id": ""})
        )
