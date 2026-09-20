"""Тесты frontend proxy API для scheduler."""

from __future__ import annotations

import pytest

from apps.crm_worker.tasks.task_names import (
    CRM_RECONCILE_DAILY_SUMMARY,
    CRM_REEMBED_STALE_DOCUMENTS,
)
from apps.idle_worker.tasks.task_names import (
    TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK,
    TASK_CALENDAR_SYNC_TICK,
    TASK_FILE_RETENTION_PURGE_TICK,
    TASK_SPAN_BILLING_SETTLEMENT_TICK,
)
from apps.rag_worker.tasks.task_names import (
    RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK,
    RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK,
    RAG_REEMBED_STALE_DOCUMENTS_TICK,
)
from apps.scheduler.main import (
    CRM_RECONCILE_DAILY_SUMMARY_CRON,
    SYSTEM_SCHEDULER_COMPANY_ID,
    on_startup,
)
from core.config.models import (
    BillingConfig,
    BillingSpanSettlementConfig,
    CalendarSyncConfig,
    FilesConfig,
    LLMConfig,
    MailSyncConfig,
    MCPCatalogConfig,
    PaymentProvidersConfig,
    RAGConfig,
)
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleType,
    ScheduledTaskStatus,
)


@pytest.mark.asyncio
async def test_scheduler_startup_creates_calendar_sync_schedule_when_missing() -> None:
    class _FakeSettings:
        calendar_sync = CalendarSyncConfig(
            enabled=True,
            cron="*/15 * * * *",
        )
        mail_sync = MailSyncConfig(enabled=False)
        billing = BillingConfig()
        llm = LLMConfig()
        payment_providers = PaymentProvidersConfig()
        rag = RAGConfig()
        files = FilesConfig()
        mcp_catalog = MCPCatalogConfig()

    class _FakeSchedulerService:
        def __init__(self) -> None:
            self.created_requests: list = []

        async def list(self, company_id, filters):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            if filters.task_name == TASK_CALENDAR_SYNC_TICK.name:
                return []
            if filters.task_name == TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name:
                return []
            if filters.task_name == TASK_SPAN_BILLING_SETTLEMENT_TICK.name:
                return []
            if filters.task_name == RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK.name:
                return []
            if filters.task_name == RAG_REEMBED_STALE_DOCUMENTS_TICK.name:
                return []
            if filters.task_name == RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK.name:
                return []
            if filters.task_name == CRM_REEMBED_STALE_DOCUMENTS.name:
                return []
            if filters.task_name == CRM_RECONCILE_DAILY_SUMMARY.name:
                return []
            if filters.task_name == TASK_FILE_RETENTION_PURGE_TICK.name:
                return []
            raise AssertionError(f"unexpected task_name={filters.task_name!r}")

        async def create(self, company_id, user_id, request):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            assert user_id is None
            self.created_requests.append(request)
            n = len(self.created_requests)
            return type(
                "CreatedTask",
                (),
                {"schedule_task_id": f"task-{n}", "schedule_id": f"schedule-{n}"},
            )()

    fake_service = _FakeSchedulerService()
    fake_container = type("Container", (), {"scheduler_service": fake_service})()

    await on_startup(app=None, container=fake_container, settings=_FakeSettings())

    assert len(fake_service.created_requests) == 8
    names = {r.task_name for r in fake_service.created_requests}
    assert names == {
        TASK_CALENDAR_SYNC_TICK.name,
        TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name,
        TASK_FILE_RETENTION_PURGE_TICK.name,
        RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK.name,
        RAG_REEMBED_STALE_DOCUMENTS_TICK.name,
        RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK.name,
        CRM_REEMBED_STALE_DOCUMENTS.name,
        CRM_RECONCILE_DAILY_SUMMARY.name,
    }
    by_name = {r.task_name: r for r in fake_service.created_requests}
    assert by_name[TASK_CALENDAR_SYNC_TICK.name].schedule_type == PlatformScheduleType.CRON
    assert by_name[TASK_CALENDAR_SYNC_TICK.name].cron == "*/15 * * * *"
    assert (
        by_name[TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name].schedule_type == PlatformScheduleType.CRON
    )
    assert by_name[TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name].cron == "*/15 * * * *"
    assert (
        by_name[RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK.name].schedule_type == PlatformScheduleType.CRON
    )
    assert by_name[CRM_RECONCILE_DAILY_SUMMARY.name].queue_name == "crm_summary"
    assert by_name[CRM_RECONCILE_DAILY_SUMMARY.name].cron == CRM_RECONCILE_DAILY_SUMMARY_CRON


@pytest.mark.asyncio
async def test_scheduler_startup_resumes_paused_calendar_sync_schedule() -> None:
    paused_task = type(
        "PausedTask",
        (),
        {"schedule_task_id": "paused-1", "status": ScheduledTaskStatus.PAUSED},
    )()

    class _FakeSettings:
        calendar_sync = CalendarSyncConfig(
            enabled=True,
            cron="*/15 * * * *",
        )
        mail_sync = MailSyncConfig(enabled=False)
        billing = BillingConfig()
        llm = LLMConfig()
        payment_providers = PaymentProvidersConfig()
        rag = RAGConfig()
        files = FilesConfig()
        mcp_catalog = MCPCatalogConfig()

    class _FakeSchedulerService:
        def __init__(self) -> None:
            self.resumed_schedule_task_id = None
            self.meeting_reminder_create = None

        async def list(self, company_id, filters):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            if filters.task_name == TASK_CALENDAR_SYNC_TICK.name:
                return [paused_task]
            if filters.task_name == TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name:
                return []
            if filters.task_name == TASK_SPAN_BILLING_SETTLEMENT_TICK.name:
                return []
            if filters.task_name == RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK.name:
                return []
            if filters.task_name == RAG_REEMBED_STALE_DOCUMENTS_TICK.name:
                return []
            if filters.task_name == RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK.name:
                return []
            if filters.task_name == CRM_REEMBED_STALE_DOCUMENTS.name:
                return []
            if filters.task_name == CRM_RECONCILE_DAILY_SUMMARY.name:
                return []
            if filters.task_name == TASK_FILE_RETENTION_PURGE_TICK.name:
                return []
            raise AssertionError(f"unexpected task_name={filters.task_name!r}")

        async def resume(self, company_id, schedule_task_id):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            self.resumed_schedule_task_id = schedule_task_id
            return type(
                "ResumedTask",
                (),
                {
                    "schedule_task_id": schedule_task_id,
                    "schedule_id": "schedule-2",
                    "status": ScheduledTaskStatus.PENDING,
                    "cron": "*/15 * * * *",
                    "payload": {
                        "schedule_task_id": schedule_task_id,
                        "company_id": SYSTEM_SCHEDULER_COMPANY_ID,
                    },
                },
            )()

        async def get_redis_snapshot(self, company_id, schedule_task_id):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            return PlatformRedisScheduleSnapshot(
                schedule_task_id=schedule_task_id,
                company_id=company_id,
                schedule_id="schedule-2",
                exists_in_redis=True,
                status=ScheduledTaskStatus.PENDING,
                task_name=TASK_CALENDAR_SYNC_TICK.name,
                cron="*/15 * * * *",
                kwargs={
                    "schedule_task_id": schedule_task_id,
                    "company_id": company_id,
                },
            )

        async def reconcile_cron(
            self,
            company_id,
            schedule_task_id,
            cron,
            payload,
            recreate_schedule=False,
        ):
            return type(
                "ReconciledTask",
                (),
                {
                    "schedule_task_id": schedule_task_id,
                    "schedule_id": "schedule-2",
                    "status": ScheduledTaskStatus.PENDING,
                    "cron": cron,
                    "payload": {
                        "schedule_task_id": schedule_task_id,
                        "company_id": company_id,
                        **payload,
                    },
                },
            )()

        async def create(self, company_id, user_id, request):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            assert user_id is None
            if request.task_name == TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name:
                self.meeting_reminder_create = request
            return type(
                "CreatedTask",
                (),
                {
                    "schedule_task_id": f"created-{request.task_name}",
                    "schedule_id": "schedule-rem-1",
                },
            )()

    fake_service = _FakeSchedulerService()
    fake_container = type("Container", (), {"scheduler_service": fake_service})()

    await on_startup(app=None, container=fake_container, settings=_FakeSettings())

    assert fake_service.resumed_schedule_task_id == "paused-1"
    assert fake_service.meeting_reminder_create is not None
    assert (
        fake_service.meeting_reminder_create.task_name == TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name
    )


@pytest.mark.asyncio
async def test_scheduler_startup_creates_span_billing_schedule_when_enabled() -> None:
    class _FakeSettings:
        calendar_sync = CalendarSyncConfig(enabled=False, sync_meeting_reminder_enabled=False)
        mail_sync = MailSyncConfig(enabled=False)
        billing = BillingConfig(
            span_settlement=BillingSpanSettlementConfig(
                enabled=True,
                cron="*/5 * * * *",
            )
        )
        llm = LLMConfig()
        payment_providers = PaymentProvidersConfig()
        rag = RAGConfig()
        files = FilesConfig()
        mcp_catalog = MCPCatalogConfig()

    class _FakeSchedulerService:
        def __init__(self) -> None:
            self.created_requests: list = []

        async def list(self, company_id, filters):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            return []

        async def create(self, company_id, user_id, request):
            assert company_id == SYSTEM_SCHEDULER_COMPANY_ID
            assert user_id is None
            self.created_requests.append(request)
            n = len(self.created_requests)
            return type(
                "CreatedTask",
                (),
                {"schedule_task_id": f"task-{n}", "schedule_id": f"schedule-{n}"},
            )()

    fake_service = _FakeSchedulerService()
    fake_container = type("Container", (), {"scheduler_service": fake_service})()

    await on_startup(app=None, container=fake_container, settings=_FakeSettings())

    span_reqs = [
        r for r in fake_service.created_requests if r.task_name == TASK_SPAN_BILLING_SETTLEMENT_TICK.name
    ]
    assert len(span_reqs) == 1
    assert span_reqs[0].schedule_type == PlatformScheduleType.CRON
    assert span_reqs[0].cron == "*/5 * * * *"
    assert span_reqs[0].queue_name == "idle"
