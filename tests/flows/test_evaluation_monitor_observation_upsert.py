"""Повторная запись наблюдения монитора evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.flows.di import FlowsDi
from apps.flows.src.models.evaluation_lab import (
    EvaluationMonitorObservation,
    EvaluationMonitorObservationState,
)


@pytest.mark.asyncio
async def test_upsert_by_monitor_and_trace_keeps_state_after_curation(
    di: FlowsDi,
    unique_id: str,
) -> None:
    _ = di
    sampled_at = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    monitor_id = f"mon-{unique_id}"
    trace_id = f"trace-{unique_id}"
    created = await EvaluationMonitorObservation.upsert_by_monitor_and_trace(
        EvaluationMonitorObservation(
            observation_id=f"obs-{unique_id}",
            monitor_id=monitor_id,
            suite_id=f"suite-{unique_id}",
            flow_id=f"flow-{unique_id}",
            branch_id="main",
            trace_id=trace_id,
            state=EvaluationMonitorObservationState.SAMPLED,
            span_count=1,
            payload={},
            sampled_at=sampled_at,
            company_id="system",
        )
    )
    refreshed = await EvaluationMonitorObservation.upsert_by_monitor_and_trace(
        created.model_copy(
            update={
                "observation_id": f"other-{unique_id}",
                "state": EvaluationMonitorObservationState.CURATED,
                "span_count": 3,
            }
        )
    )
    assert refreshed.observation_id == created.observation_id
    assert refreshed.state == EvaluationMonitorObservationState.CURATED
    assert refreshed.span_count == 3

    refreshed.curated_case_id = f"case-{unique_id}"
    _ = await refreshed.save()
    frozen = await EvaluationMonitorObservation.upsert_by_monitor_and_trace(
        refreshed.model_copy(
            update={
                "state": EvaluationMonitorObservationState.SAMPLED,
                "span_count": 4,
            }
        )
    )
    assert frozen.observation_id == created.observation_id
    assert frozen.curated_case_id == f"case-{unique_id}"
    assert frozen.state == EvaluationMonitorObservationState.CURATED
    assert frozen.span_count == 4
    assert await EvaluationMonitorObservation.for_trace(monitor_id, f"missing-{unique_id}") is None
    with pytest.raises(ValueError, match="monitor_id and trace_id are required"):
        _ = await EvaluationMonitorObservation.upsert_by_monitor_and_trace(
            created.model_copy(update={"trace_id": ""})
        )
