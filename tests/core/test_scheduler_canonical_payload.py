"""Нормализация kwargs платформенных расписаний."""

from core.scheduler.service import SchedulerService


def test_canonical_payload_strips_legacy_scheduler_task_id() -> None:
    payload = SchedulerService._canonical_payload(
        {
            "scheduler_task_id": "legacy-id",
            "company_id": "wrong-company",
            "system_task": "marker",
        },
        company_id="system",
        schedule_task_id="canonical-id",
    )
    assert payload == {
        "system_task": "marker",
        "schedule_task_id": "canonical-id",
        "company_id": "system",
    }
    assert "scheduler_task_id" not in payload


def test_canonical_payload_prefers_authoritative_schedule_task_id() -> None:
    payload = SchedulerService._canonical_payload(
        {
            "schedule_task_id": "stale-id",
            "scheduler_task_id": "legacy-id",
        },
        company_id="system",
        schedule_task_id="authoritative-id",
    )
    assert payload["schedule_task_id"] == "authoritative-id"
    assert "scheduler_task_id" not in payload
