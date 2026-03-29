"""Тесты frontend proxy API для scheduler."""

from __future__ import annotations

import datetime

import pytest

from apps.scheduler.main import (
    CALENDAR_SYNC_TASK_NAME,
    SYSTEM_SCHEDULER_COMPANY_ID,
    on_startup,
)
from core.scheduler.models import PlatformScheduleType, ScheduledTaskStatus


@pytest.mark.asyncio
class TestFrontendSchedulerApi:
    @staticmethod
    def _task_payload(status: str = "pending") -> dict:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {
            "id": "task-1",
            "company_id": "system",
            "schedule_id": "sched-1",
            "target_service": "flows",
            "task_name": "sync_llm_models_task",
            "queue_name": "default",
            "schedule_type": "interval",
            "cron": None,
            "interval_seconds": 60,
            "run_at": None,
            "timezone": "UTC",
            "payload": {},
            "status": status,
            "created_by_user_id": "test-user",
            "created_at": now,
            "updated_at": now,
            "last_run_at": None,
            "next_run_at": None,
            "error_message": None,
        }

    async def test_list_schedules(self, frontend_client_with_auth, frontend_container, monkeypatch):
        async def _list(filters):
            return [self._task_payload()]

        monkeypatch.setattr(frontend_container.scheduler_client, "list_schedules", _list)

        response = await frontend_client_with_auth.get("/frontend/api/scheduler/schedules")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert payload[0]["id"] == "task-1"
        assert payload[0]["target_service"] == "flows"

    async def test_pause_schedule(self, frontend_client_with_auth, frontend_container, monkeypatch):
        async def _pause(task_id: str):
            assert task_id == "task-1"
            payload = self._task_payload(status="paused")
            payload["schedule_id"] = None
            return payload

        monkeypatch.setattr(frontend_container.scheduler_client, "pause_schedule", _pause)

        response = await frontend_client_with_auth.post("/frontend/api/scheduler/schedules/task-1/pause")
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "task-1"
        assert payload["status"] == "paused"

    async def test_run_now_schedule(self, frontend_client_with_auth, frontend_container, monkeypatch):
        async def _run_now(task_id: str):
            assert task_id == "task-1"
            payload = self._task_payload()
            payload["last_run_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            return payload

        monkeypatch.setattr(frontend_container.scheduler_client, "run_schedule_now", _run_now)

        response = await frontend_client_with_auth.post("/frontend/api/scheduler/schedules/task-1/run-now")
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "task-1"

    async def test_get_schedule(self, frontend_client_with_auth, frontend_container, monkeypatch):
        async def _get(task_id: str):
            assert task_id == "task-1"
            return self._task_payload()

        monkeypatch.setattr(frontend_container.scheduler_client, "get_schedule", _get)

        response = await frontend_client_with_auth.get("/frontend/api/scheduler/schedules/task-1")
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "task-1"
        assert payload["target_service"] == "flows"

    async def test_create_schedule(self, frontend_client_with_auth, frontend_container, monkeypatch):
        async def _create(request):
            assert request.target_service == "flows"
            assert request.task_name == "sync_llm_models_task"
            assert request.schedule_type == "interval"
            assert request.interval_seconds == 60
            return self._task_payload()

        monkeypatch.setattr(frontend_container.scheduler_client, "create_schedule", _create)

        response = await frontend_client_with_auth.post(
            "/frontend/api/scheduler/schedules",
            json={
                "target_service": "flows",
                "task_name": "sync_llm_models_task",
                "queue_name": "default",
                "schedule_type": "interval",
                "interval_seconds": 60,
                "payload": {},
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "task-1"

    async def test_resume_schedule(self, frontend_client_with_auth, frontend_container, monkeypatch):
        async def _resume(task_id: str):
            assert task_id == "task-1"
            return self._task_payload(status="pending")

        monkeypatch.setattr(frontend_container.scheduler_client, "resume_schedule", _resume)

        response = await frontend_client_with_auth.post("/frontend/api/scheduler/schedules/task-1/resume")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "pending"

    async def test_cancel_schedule(self, frontend_client_with_auth, frontend_container, monkeypatch):
        async def _cancel(task_id: str):
            assert task_id == "task-1"
            return self._task_payload(status="cancelled")

        monkeypatch.setattr(frontend_container.scheduler_client, "cancel_schedule", _cancel)

        response = await frontend_client_with_auth.post("/frontend/api/scheduler/schedules/task-1/cancel")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "cancelled"


@pytest.mark.asyncio
async def test_scheduler_startup_creates_calendar_sync_schedule_when_missing() -> None:
    class _FakeSettings:
        class _CalendarSync:
            enabled = True
            cron = "*/1 * * * *"

        calendar_sync = _CalendarSync()

    class _FakeSchedulerService:
        def __init__(self) -> None:
            self.created_request = None

        async def list(self, company_id, filters):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            assert filters.task_name == CALENDAR_SYNC_TASK_NAME
            return []

        async def create(self, company_id, user_id, request):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            assert user_id is None
            self.created_request = request
            return type("CreatedTask", (), {"id": "task-1", "schedule_id": "schedule-1"})()

    fake_service = _FakeSchedulerService()
    fake_container = type("Container", (), {"scheduler_service": fake_service})()

    await on_startup(app=None, container=fake_container, settings=_FakeSettings())

    assert fake_service.created_request is not None
    assert fake_service.created_request.task_name == CALENDAR_SYNC_TASK_NAME
    assert fake_service.created_request.schedule_type == PlatformScheduleType.CRON
    assert fake_service.created_request.cron == "*/1 * * * *"


@pytest.mark.asyncio
async def test_scheduler_startup_resumes_paused_calendar_sync_schedule() -> None:
    paused_task = type("PausedTask", (), {"id": "paused-1", "status": ScheduledTaskStatus.PAUSED})()

    class _FakeSettings:
        class _CalendarSync:
            enabled = True
            cron = "*/1 * * * *"

        calendar_sync = _CalendarSync()

    class _FakeSchedulerService:
        def __init__(self) -> None:
            self.resumed_task_id = None

        async def list(self, company_id, filters):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            assert filters.task_name == CALENDAR_SYNC_TASK_NAME
            return [paused_task]

        async def resume(self, company_id, schedule_task_id):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            self.resumed_task_id = schedule_task_id
            return type("ResumedTask", (), {"id": schedule_task_id, "schedule_id": "schedule-2"})()

    fake_service = _FakeSchedulerService()
    fake_container = type("Container", (), {"scheduler_service": fake_service})()

    await on_startup(app=None, container=fake_container, settings=_FakeSettings())

    assert fake_service.resumed_task_id == "paused-1"
