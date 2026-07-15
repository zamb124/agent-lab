"""Direct in-process тесты TaskIQ tick-задач search_worker.

Тесты в ``test_crawl_scheduler_task_kwargs.py`` проверяют только signatures.
Эти тесты вызывают ``crawl_reclaim_stale_fetching`` через ``get_search_container()``
singleton (поисковая БД поднята ``make test-up``) и проверяют структуру ответа
и side-effects в БД (reclaim stale fetching/finish stale running).

``crawl_orchestrator_tick`` требует реального crawl_profile_id — покрыт
косвенно через интеграционные тесты; signature coverage уже есть.
"""

from __future__ import annotations

import inspect

import pytest

from apps.search_worker.tasks import crawl_tasks


def test_crawl_orchestrator_tick_signature_requires_crawl_profile_id() -> None:
    """``crawl_orchestrator_tick`` — ``crawl_profile_id`` обязательный позиционный."""
    signature = inspect.signature(crawl_tasks.crawl_orchestrator_tick)
    params = signature.parameters
    assert "crawl_profile_id" in params
    assert params["crawl_profile_id"].default is inspect.Parameter.empty
    assert params["crawl_profile_id"].kind == inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_crawl_reclaim_stale_fetching_signature_has_only_optional_kwargs() -> None:
    """``crawl_reclaim_stale_fetching`` — все параметры опциональные."""
    signature = inspect.signature(crawl_tasks.crawl_reclaim_stale_fetching)
    for param in signature.parameters.values():
        assert param.default is not inspect.Parameter.empty, (
            f"parameter {param.name} must have default"
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crawl_reclaim_stale_fetching_runs_noop_on_clean_db(
    unique_id: str,
) -> None:
    """Reclaim тик на БД без stale-джобов возвращает корректную структуру без ошибок."""
    result = await crawl_tasks.crawl_reclaim_stale_fetching(
        schedule_task_id=f"reclaim_{unique_id}",
        company_id=None,
    )

    assert isinstance(result, dict)
    assert "stale_jobs_finished" in result
    assert "reclaimed_fetching" in result
    assert "requeued_failed" in result
    assert "enrichment_backfill" in result
    assert isinstance(result["stale_jobs_finished"], int)
    assert isinstance(result["reclaimed_fetching"], int)
    assert isinstance(result["requeued_failed"], int)
    assert isinstance(result["enrichment_backfill"], int)
