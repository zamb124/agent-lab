"""Reconcile crawl cron schedules in scheduler bootstrap."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from apps.scheduler.crawl_schedule_bootstrap import (
    CRAWL_ORCHESTRATOR_BACKUP_CRON,
    CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID,
    ensure_search_crawl_schedules,
)
from apps.search_worker.tasks.task_names import CRAWL_ORCHESTRATOR_TICK_TASK_NAME
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)

SYSTEM_SCHEDULER_COMPANY_ID = "system"


class _InMemorySchedulerService:
    def __init__(self, tasks: list[PlatformScheduledTask] | None = None) -> None:
        self.tasks = list(tasks or [])
        self.reconcile_cron_calls: list[dict[str, Any]] = []

    async def list(
        self,
        *,
        company_id: str,
        filters: PlatformScheduleFilter,
    ) -> list[PlatformScheduledTask]:
        return [
            task
            for task in self.tasks
            if task.company_id == company_id
            and (filters.task_name is None or task.task_name == filters.task_name)
        ]

    async def create(
        self,
        *,
        company_id: str,
        user_id: str | None,
        request: PlatformScheduleCreateRequest,
    ) -> PlatformScheduledTask:
        task = PlatformScheduledTask(
            schedule_task_id=f"created-{len(self.tasks) + 1}",
            company_id=company_id,
            schedule_id=f"redis-{len(self.tasks) + 1}",
            target_service=request.target_service,
            task_name=request.task_name,
            queue_name=request.queue_name,
            schedule_type=request.schedule_type,
            cron=request.cron,
            interval_seconds=request.interval_seconds,
            run_at=request.run_at,
            timezone=request.timezone,
            payload={
                **dict(request.payload),
                "schedule_task_id": f"created-{len(self.tasks) + 1}",
                "company_id": company_id,
            },
            status=ScheduledTaskStatus.PENDING,
            created_by_user_id=user_id,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.tasks.append(task)
        return task

    async def resume(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
    ) -> PlatformScheduledTask:
        raise AssertionError("resume should not be called in this test")

    async def get_redis_snapshot(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
    ) -> PlatformRedisScheduleSnapshot:
        for task in self.tasks:
            if task.company_id == company_id and task.schedule_task_id == schedule_task_id:
                return PlatformRedisScheduleSnapshot(
                    schedule_task_id=task.schedule_task_id,
                    company_id=task.company_id,
                    schedule_id=task.schedule_id,
                    exists_in_redis=True,
                    status=task.status,
                    task_name=task.task_name,
                    cron=task.cron,
                    kwargs=task.payload,
                )
        raise AssertionError(f"task not found: {schedule_task_id}")

    async def reconcile_cron(
        self,
        *,
        company_id: str,
        schedule_task_id: str,
        cron: str,
        payload: dict[str, Any],
        recreate_schedule: bool = False,
    ) -> PlatformScheduledTask:
        self.reconcile_cron_calls.append(
            {
                "schedule_task_id": schedule_task_id,
                "cron": cron,
                "payload": payload,
                "recreate_schedule": recreate_schedule,
            }
        )
        for index, task in enumerate(self.tasks):
            if task.company_id == company_id and task.schedule_task_id == schedule_task_id:
                repaired = task.model_copy(
                    update={
                        "cron": cron,
                        "payload": {
                            **dict(payload),
                            "schedule_task_id": schedule_task_id,
                            "company_id": company_id,
                        },
                    }
                )
                self.tasks[index] = repaired
                return repaired
        raise AssertionError(f"task not found: {schedule_task_id}")


class _Container:
    def __init__(self, service: _InMemorySchedulerService) -> None:
        self.scheduler_service = service


def _orchestrator_task(*, cron: str) -> PlatformScheduledTask:
    return PlatformScheduledTask(
        schedule_task_id="crawl-tick-old",
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        schedule_id="redis-crawl-tick-old",
        target_service="search",
        task_name=CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
        queue_name="search",
        schedule_type=PlatformScheduleType.CRON,
        cron=cron,
        timezone="UTC",
        payload={
            "crawl_profile_id": CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID,
            "schedule_task_id": "crawl-tick-old",
            "company_id": SYSTEM_SCHEDULER_COMPANY_ID,
        },
        status=ScheduledTaskStatus.PENDING,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_ensure_search_crawl_schedules_reconciles_legacy_orchestrator_cron() -> None:
    service = _InMemorySchedulerService([_orchestrator_task(cron="0 */6 * * *")])
    container = _Container(service)

    await ensure_search_crawl_schedules(container=container)

    assert len(service.reconcile_cron_calls) == 1
    assert service.reconcile_cron_calls[0]["cron"] == CRAWL_ORCHESTRATOR_BACKUP_CRON
    assert service.tasks[0].cron == CRAWL_ORCHESTRATOR_BACKUP_CRON
