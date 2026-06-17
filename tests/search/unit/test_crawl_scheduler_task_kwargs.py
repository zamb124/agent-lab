"""Scheduler kwargs accepted by crawl TaskIQ tasks."""

from __future__ import annotations

import inspect

from apps.search_worker.tasks import crawl_tasks


def test_crawl_orchestrator_tick_accepts_scheduler_company_id_kwarg() -> None:
    signature = inspect.signature(crawl_tasks.crawl_orchestrator_tick)
    assert "company_id" in signature.parameters
    assert "schedule_task_id" in signature.parameters


def test_crawl_reclaim_stale_fetching_accepts_scheduler_kwargs() -> None:
    signature = inspect.signature(crawl_tasks.crawl_reclaim_stale_fetching)
    assert "company_id" in signature.parameters
    assert "schedule_task_id" in signature.parameters
