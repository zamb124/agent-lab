"""Direct in-process тесты TaskIQ tick-задач rag_worker.

Покрытие: ``rag_cleanup_expired_documents_tick`` (maintenance_tasks.py),
``rag_reembed_stale_documents_tick`` и ``rag_cleanup_orphan_company_chunks_tick``
частично покрыты в ``tests/core/rag/test_execute_reembed_tick_integration.py``;
эти тесты добавляют disabled-path и validation-path coverage.
"""

from __future__ import annotations

import pytest

from apps.rag.tasks import maintenance_tasks


@pytest.mark.asyncio
async def test_rag_cleanup_expired_documents_tick_skips_when_disabled(
    unique_id: str,
    rag_worker_di,
) -> None:
    """``rag.ttl.cleanup_enabled=false`` → no-op skip response."""
    from core.config import get_settings

    settings = get_settings()
    original = settings.rag.ttl.cleanup_enabled
    settings.rag.ttl.cleanup_enabled = False
    try:
        result = await maintenance_tasks.rag_cleanup_expired_documents_tick(
            schedule_task_id=f"skip_{unique_id}",
            company_id=None,
            di=rag_worker_di,
        )
    finally:
        settings.rag.ttl.cleanup_enabled = original

    assert result["skipped"] is True
    assert result["candidates_total"] == 0
    assert result["deleted_documents"] == 0
    assert result["failed_documents"] == 0
    assert result["schedule_task_id"] == f"skip_{unique_id}"


@pytest.mark.asyncio
async def test_rag_cleanup_expired_documents_tick_runs_batch(
    unique_id: str,
    rag_worker_di,
) -> None:
    """Тик с ``cleanup_enabled=true`` на пустой shared БД возвращает нули без ошибок."""
    from core.config import get_settings

    settings = get_settings()
    original = settings.rag.ttl.cleanup_enabled
    settings.rag.ttl.cleanup_enabled = True
    try:
        result = await maintenance_tasks.rag_cleanup_expired_documents_tick(
            schedule_task_id=f"run_{unique_id}",
            company_id=None,
            di=rag_worker_di,
        )
    finally:
        settings.rag.ttl.cleanup_enabled = original

    assert result["skipped"] is False
    assert isinstance(result["candidates_total"], int)
    assert isinstance(result["deleted_documents"], int)
    assert isinstance(result["failed_documents"], int)
    assert result["candidates_total"] >= 0


@pytest.mark.asyncio
async def test_rag_reembed_stale_documents_tick_requires_schedule_task_id(
    rag_worker_di,
) -> None:
    """Reembed тик требует ``schedule_task_id`` (validation gate)."""
    with pytest.raises(ValueError, match="schedule_task_id"):
        await maintenance_tasks.rag_reembed_stale_documents_tick(schedule_task_id="  ", di=rag_worker_di)
    with pytest.raises(ValueError, match="schedule_task_id"):
        await maintenance_tasks.rag_reembed_stale_documents_tick(schedule_task_id="", di=rag_worker_di)
