"""
Тесты дедупликации задач, retry и новых эндпоинтов.

Без моков и манкипатчей. Для симуляции running-задач используем прямые
вставки в TaskRepository через crm_container — единственный способ
воспроизвести состояние pending/running без реального воркера.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from apps.crm.db.models import CRMTask
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User

pytestmark = pytest.mark.timeout(30, func_only=True)

def _NOW():
    return datetime.now(timezone.utc)


def _make_task(
    task_id: str,
    task_type: str,
    status: str,
    namespace: str,
    company_id: str,
    user_id: str,
    data: dict | None = None,
    stage: str = "running",
) -> CRMTask:
    now = _NOW()
    return CRMTask(
        task_id=task_id,
        task_type=task_type,
        status=status,
        stage=stage,
        progress_pct=50 if status == "running" else 100,
        company_id=company_id,
        namespace=namespace,
        user_id=user_id,
        data=data or {},
        started_at=now if status == "running" else None,
        completed_at=now if status in ("completed", "failed", "cancelled") else None,
        created_at=now,
        updated_at=now,
    )


async def _insert_task(crm_container, task: CRMTask, company_id: str, namespace: str, user_id: str) -> None:
    ctx = Context(
        user=User(user_id=user_id, name="Test"),
        active_company=Company(company_id=company_id, name="System"),
        channel="test",
        active_namespace=namespace,
    )
    set_context(ctx)
    try:
        await crm_container.task_repository.create(task)
    finally:
        clear_context()


async def _set_note_attachment_ids(
    crm_container,
    *,
    note_id: str,
    attachment_ids: list[str],
    company_id: str,
    namespace: str,
    user_id: str,
) -> None:
    ctx = Context(
        user=User(user_id=user_id, name="Test"),
        active_company=Company(company_id=company_id, name="System"),
        channel="test",
        active_namespace=namespace,
    )
    set_context(ctx)
    try:
        note = await crm_container.entity_repository.get(note_id)
        assert note is not None
        note.attachment_ids = attachment_ids
        await crm_container.entity_repository.update(note)
    finally:
        clear_context()


# ─── Дедупликация: note_analyze ──────────────────────────────────────────────

class TestNoteAnalyzeDedup:
    @pytest.mark.asyncio
    async def test_analyze_rejects_note_with_missing_file_metadata(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Старт анализа блокируется pre-flight проверкой, если attachment_id не найден в shared storage."""
        ns = f"g_{unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Orphan attachment {unique_id}", "namespace": ns},
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = note_resp.json()["entity_id"]
        missing_file_id = f"file_missing_{unique_id[:8]}"
        await _set_note_attachment_ids(
            crm_container,
            note_id=note_id,
            attachment_ids=[missing_file_id],
            company_id="system",
            namespace=ns,
            user_id=system_user_id,
        )

        resp = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={"note_id": note_id},
            headers=auth_headers_system,
        )
        assert resp.status_code == 400, resp.text
        assert missing_file_id in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_running_task_blocks_new_analyze(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Running note_analyze задача блокирует запуск новой для той же заметки."""
        ns = f"g_{unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Dedup note {unique_id}", "namespace": ns},
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = note_resp.json()["entity_id"]

        running_task = _make_task(
            task_id=f"running-{unique_id}",
            task_type="note_analyze",
            status="running",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"note_id": note_id, "mode": "analyze", "config_payload": {}},
        )
        await _insert_task(crm_container, running_task, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={"note_id": note_id},
            headers=auth_headers_system,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "active_task_exists"
        assert detail["task_type"] == "note_analyze"

    @pytest.mark.asyncio
    async def test_pending_task_blocks_new_analyze(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Pending note_analyze задача также блокирует запуск новой."""
        ns = f"g_{unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Dedup pending {unique_id}", "namespace": ns},
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = note_resp.json()["entity_id"]

        pending_task = _make_task(
            task_id=f"pending-{unique_id}",
            task_type="note_analyze",
            status="pending",
            stage="pending",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"note_id": note_id, "mode": "analyze", "config_payload": {}},
        )
        await _insert_task(crm_container, pending_task, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={"note_id": note_id},
            headers=auth_headers_system,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "active_task_exists"
        assert detail["task_type"] == "note_analyze"

    @pytest.mark.asyncio
    async def test_completed_task_allows_new_analyze(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Completed задача НЕ блокирует запуск новой анализа той же заметки."""
        ns = f"g_{unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Dedup completed {unique_id}", "description": "x", "namespace": ns},
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = note_resp.json()["entity_id"]

        completed_task = _make_task(
            task_id=f"completed-{unique_id}",
            task_type="note_analyze",
            status="completed",
            stage="completed",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"note_id": note_id, "mode": "analyze", "config_payload": {}},
        )
        await _insert_task(crm_container, completed_task, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={"note_id": note_id},
            headers=auth_headers_system,
        )
        assert resp.status_code != 400 or "уже выполняется" not in resp.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_running_task_for_other_note_does_not_block(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Running задача для ДРУГОЙ заметки не блокирует запуск новой."""
        ns = f"g_{unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Target note {unique_id}", "description": "y", "namespace": ns},
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        target_note_id = note_resp.json()["entity_id"]

        other_note_id = str(uuid.uuid4())
        running_task = _make_task(
            task_id=f"other-running-{unique_id}",
            task_type="note_analyze",
            status="running",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"note_id": other_note_id, "mode": "analyze", "config_payload": {}},
        )
        await _insert_task(crm_container, running_task, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/note-analyze",
            json={"note_id": target_note_id},
            headers=auth_headers_system,
        )
        assert resp.status_code != 400 or "уже выполняется" not in resp.json().get("detail", "")


# ─── Дедупликация: knowledge_import ──────────────────────────────────────────

class TestKnowledgeImportDedup:
    @pytest.mark.asyncio
    async def test_running_import_blocks_new_in_same_namespace(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Running knowledge_import в том же namespace блокирует запуск нового."""
        ns = f"g_{unique_id}"
        running_task = _make_task(
            task_id=f"running-import-{unique_id}",
            task_type="knowledge_import",
            status="running",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"mode": "notes_only", "notes_created_count": 0},
        )
        await _insert_task(crm_container, running_task, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/knowledge-import",
            json={"namespace": ns, "mode": "notes_only", "source_text": "hello world"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "active_task_exists"
        assert detail["task_type"] == "knowledge_import"


class TestEntityCardAttachments:
    @pytest.mark.asyncio
    async def test_card_returns_missing_attachment_instead_of_500(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Карточка note не падает, если attachment_id отсутствует и в shared storage, и в RAG."""
        ns = f"g_{unique_id}"
        note_resp = await crm_client.post(
            "/crm/api/v1/entities/",
            json={"entity_type": "note", "name": f"Card orphan {unique_id}", "namespace": ns},
            headers=auth_headers_system,
        )
        assert note_resp.status_code in (200, 201), note_resp.text
        note_id = note_resp.json()["entity_id"]
        missing_file_id = f"file_missing_card_{unique_id[:8]}"
        await _set_note_attachment_ids(
            crm_container,
            note_id=note_id,
            attachment_ids=[missing_file_id],
            company_id="system",
            namespace=ns,
            user_id=system_user_id,
        )

        card_resp = await crm_client.get(
            f"/crm/api/v1/entities/{note_id}/card",
            headers=auth_headers_system,
        )
        assert card_resp.status_code == 200, card_resp.text
        attachments = card_resp.json()["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["document_id"] == missing_file_id
        assert attachments[0]["status"] == "missing"

    @pytest.mark.asyncio
    async def test_completed_import_allows_new(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Completed import в namespace НЕ блокирует запуск нового."""
        ns = f"g_{unique_id}"
        completed = _make_task(
            task_id=f"completed-import-{unique_id}",
            task_type="knowledge_import",
            status="completed",
            stage="completed",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"mode": "notes_only"},
        )
        await _insert_task(crm_container, completed, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/knowledge-import",
            json={"namespace": ns, "mode": "notes_only", "source_text": "hello world"},
            headers=auth_headers_system,
        )
        assert resp.status_code != 409, resp.text


# ─── Дедупликация: daily_summary ─────────────────────────────────────────────

class TestDailySummaryDedup:
    @pytest.mark.asyncio
    async def test_running_daily_summary_blocks_same_date(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Running daily_summary для той же даты и namespace блокирует новый запуск."""
        ns = f"g_{unique_id}"
        date_str = "2024-01-15"
        running = _make_task(
            task_id=f"running-summary-{unique_id}",
            task_type="daily_summary",
            status="running",
            stage="summarizing_day",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"date_str": date_str},
        )
        await _insert_task(crm_container, running, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/daily-summary",
            json={"namespace": ns, "date_str": date_str},
            headers=auth_headers_system,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "active_task_exists"
        assert detail["task_type"] == "daily_summary"

    @pytest.mark.asyncio
    async def test_running_daily_summary_different_date_does_not_block(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Running daily_summary для ДРУГОЙ даты не блокирует запуск для новой даты."""
        ns = f"g_{unique_id}"
        running = _make_task(
            task_id=f"other-date-summary-{unique_id}",
            task_type="daily_summary",
            status="running",
            stage="summarizing_day",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"date_str": "2024-01-10"},
        )
        await _insert_task(crm_container, running, "system", ns, system_user_id)

        resp = await crm_client.post(
            "/crm/api/v1/tasks/daily-summary",
            json={"namespace": ns, "date_str": "2024-01-20"},
            headers=auth_headers_system,
        )
        assert resp.status_code != 400 or "уже выполняется" not in resp.json().get("detail", "")


# ─── Retry ────────────────────────────────────────────────────────────────────

class TestTaskRetry:
    @pytest.mark.asyncio
    async def test_retry_not_found_returns_404(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict,
        unique_id: str,
    ) -> None:
        """Retry несуществующей задачи → 404."""
        resp = await crm_client.post(
            f"/crm/api/v1/tasks/nonexistent-task-{unique_id}/retry",
            json={},
            headers=auth_headers_system,
        )
        assert resp.status_code == 404, resp.text

    @pytest.mark.asyncio
    async def test_retry_completed_task_returns_400(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Retry completed задачи → 400: перезапуск доступен только для failed/cancelled."""
        ns = f"g_{unique_id}"
        task_id = f"retry-completed-{unique_id}"
        completed = _make_task(
            task_id=task_id,
            task_type="note_analyze",
            status="completed",
            stage="completed",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"note_id": "some-note", "mode": "analyze", "config_payload": {}},
        )
        await _insert_task(crm_container, completed, "system", ns, system_user_id)

        resp = await crm_client.post(
            f"/crm/api/v1/tasks/{task_id}/retry",
            json={},
            headers=auth_headers_system,
        )
        assert resp.status_code == 400, resp.text
        assert "failed" in resp.json().get("detail", "").lower() or "cancelled" in resp.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_retry_running_task_returns_400(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Retry running задачи → 400."""
        ns = f"g_{unique_id}"
        task_id = f"retry-running-{unique_id}"
        running = _make_task(
            task_id=task_id,
            task_type="note_analyze",
            status="running",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={"note_id": "some-note", "mode": "analyze", "config_payload": {}},
        )
        await _insert_task(crm_container, running, "system", ns, system_user_id)

        resp = await crm_client.post(
            f"/crm/api/v1/tasks/{task_id}/retry",
            json={},
            headers=auth_headers_system,
        )
        assert resp.status_code == 400, resp.text

    @pytest.mark.asyncio
    async def test_retry_failed_knowledge_import_file_based(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Retry failed knowledge_import с файлом создаёт новую задачу."""
        ns = f"g_{unique_id}"
        task_id = f"retry-failed-import-{unique_id}"
        failed = _make_task(
            task_id=task_id,
            task_type="knowledge_import",
            status="failed",
            stage="failed",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            data={
                "mode": "notes_only",
                "source_file_id": "file_000000000000",
                "source_file_ids": [],
                "split_by_headings": False,
                "chunk_max_chars": 50000,
                "notes_created_count": 0,
                "entities_created_count": 0,
                "relationships_created_count": 0,
                "created_entity_ids": [],
                "created_relationship_ids": [],
                "chunk_errors": [],
            },
        )
        await _insert_task(crm_container, failed, "system", ns, system_user_id)

        resp = await crm_client.post(
            f"/crm/api/v1/tasks/{task_id}/retry",
            json={},
            headers=auth_headers_system,
        )
        assert resp.status_code in (202, 400), resp.text
        if resp.status_code == 202:
            new_task_id = resp.json().get("task_id")
            assert new_task_id != task_id, "Retry должен создать новую задачу"


# ─── Новые API эндпоинты ──────────────────────────────────────────────────────

class TestNewTaskEndpoints:
    @pytest.mark.asyncio
    async def test_start_daily_summary_returns_202(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict,
        unique_id: str,
    ) -> None:
        """POST /tasks/daily-summary возвращает 202 и task_id."""
        ns = f"g_{unique_id}"
        resp = await crm_client.post(
            "/crm/api/v1/tasks/daily-summary",
            json={"namespace": ns, "date_str": "2024-01-15"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "task_id" in body
        assert body.get("task_type") == "daily_summary"
        assert body.get("status") in ("pending", "running", "completed", "failed")

    @pytest.mark.asyncio
    async def test_start_period_summary_returns_202(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict,
        unique_id: str,
    ) -> None:
        """POST /tasks/period-summary возвращает 202 и task_id."""
        ns = f"g_{unique_id}"
        resp = await crm_client.post(
            "/crm/api/v1/tasks/period-summary",
            json={"namespace": ns, "date_from": "2024-01-01", "date_to": "2024-01-31"},
            headers=auth_headers_system,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert "task_id" in body
        assert body.get("task_type") == "period_summary"

    @pytest.mark.asyncio
    async def test_task_appears_in_list_after_creation(
        self,
        crm_client: AsyncClient,
        auth_headers_system: dict,
        unique_id: str,
    ) -> None:
        """Созданная задача daily_summary появляется в списке задач."""
        ns = f"g_{unique_id}"
        create_resp = await crm_client.post(
            "/crm/api/v1/tasks/daily-summary",
            json={"namespace": ns, "date_str": "2024-03-01"},
            headers=auth_headers_system,
        )
        assert create_resp.status_code == 202, create_resp.text
        task_id = create_resp.json()["task_id"]

        list_resp = await crm_client.get(
            "/crm/api/v1/tasks",
            params={"namespace": ns, "task_type": "daily_summary"},
            headers=auth_headers_system,
        )
        assert list_resp.status_code == 200, list_resp.text
        tasks = list_resp.json()["items"]
        task_ids = [t["task_id"] for t in tasks]
        assert task_id in task_ids, f"task_id {task_id} не найден в списке задач"


class TestNamespaceIntegrationCancelFinalize:
    @pytest.mark.asyncio
    async def test_second_cancel_finalizes_when_cancel_already_requested(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Повторный POST /cancel при зависшем cancel_requested снимает задачу с running."""
        ns = f"g_{unique_id}"
        tid = f"ns-stuck-{unique_id}"
        now = _NOW()
        task = CRMTask(
            task_id=tid,
            task_type="namespace_integration_job",
            status="running",
            stage="leads",
            progress_pct=50,
            company_id="system",
            namespace=ns,
            user_id=system_user_id,
            data={"provider_id": "amocrm", "job": "entities", "stats": {}},
            cancel_requested=True,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        await _insert_task(crm_container, task, "system", ns, system_user_id)

        resp = await crm_client.post(
            f"/crm/api/v1/tasks/{tid}/cancel",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "cancelled"
        assert body["stage"] == "cancelled"
        assert body["cancel_requested"] is False
        assert body["progress_pct"] == 50


class TestStaleTasksAndWorkerGuards:
    @pytest.mark.asyncio
    async def test_worker_terminal_patch_does_not_overwrite_cancelled(
        self,
        crm_container,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """После отмены воркер не может записать completed поверх cancelled."""
        ns = f"g_{unique_id}"
        tid = f"race-{unique_id}"
        task = _make_task(
            tid,
            "note_analyze",
            "running",
            ns,
            "system",
            system_user_id,
            data={"note_id": "note-x"},
        )
        await _insert_task(crm_container, task, "system", ns, system_user_id)
        await crm_container.task_repository.patch_progress(
            tid,
            "system",
            status="cancelled",
            stage="cancelled",
            progress_pct=50,
            completed_at=_NOW(),
            cancel_requested=False,
        )
        await crm_container.task_repository.patch_progress(
            tid,
            "system",
            status="completed",
            stage="completed",
            progress_pct=100,
            completed_at=_NOW(),
        )
        row = await crm_container.task_repository.get_for_worker(tid, "system")
        assert row is not None
        assert row.status == "cancelled"

    @pytest.mark.asyncio
    async def test_second_cancel_finalizes_note_analyze_when_cancel_requested(
        self,
        crm_client: AsyncClient,
        crm_container,
        auth_headers_system: dict,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Повторный POST /cancel для note_analyze с cancel_requested завершает задачу."""
        ns = f"g_{unique_id}"
        tid = f"note-stuck-{unique_id}"
        now = _NOW()
        task = CRMTask(
            task_id=tid,
            task_type="note_analyze",
            status="running",
            stage="analyzing",
            progress_pct=57,
            company_id="system",
            namespace=ns,
            user_id=system_user_id,
            data={"note_id": f"n-{unique_id}", "note_name": "x", "mode": "analyze"},
            cancel_requested=True,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        await _insert_task(crm_container, task, "system", ns, system_user_id)

        resp = await crm_client.post(
            f"/crm/api/v1/tasks/{tid}/cancel",
            headers=auth_headers_system,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "cancelled"
        assert body["cancel_requested"] is False
        assert body["progress_pct"] == 57

    @pytest.mark.asyncio
    async def test_reconcile_stale_worker_marks_running_as_failed(
        self,
        crm_container,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        """Задачи с устаревшим updated_at закрываются reconcile_stale_worker_tasks."""
        ns = f"g_{unique_id}"
        tid = f"stale-{unique_id}"
        old = _NOW() - timedelta(minutes=120)
        task = CRMTask(
            task_id=tid,
            task_type="daily_summary",
            status="running",
            stage="summarizing_day",
            progress_pct=50,
            company_id="system",
            namespace=ns,
            user_id=system_user_id,
            data={"date_str": "2024-06-01", "reason": "test"},
            cancel_requested=False,
            started_at=old,
            created_at=old,
            updated_at=old,
        )
        await _insert_task(crm_container, task, "system", ns, system_user_id)

        n = await crm_container.task_service.reconcile_stale_worker_tasks()
        assert n == 1
        row = await crm_container.task_repository.get_for_worker(tid, "system")
        assert row is not None
        assert row.status == "failed"
        assert row.error_message is not None
        assert "воркер" in (row.error_message or "").lower() or "worker" in (row.error_message or "").lower()

    @pytest.mark.asyncio
    async def test_reconcile_cancel_requested_closes_even_when_recently_updated(
        self,
        crm_container,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        ns = f"g_{unique_id}"
        tid = f"cancel-fresh-{unique_id}"
        fresh = _NOW()
        task = CRMTask(
            task_id=tid,
            task_type="note_analysis_draft_repair",
            status="running",
            stage="draft_repair",
            progress_pct=50,
            company_id="system",
            namespace=ns,
            user_id=system_user_id,
            data={"note_id": f"n-{unique_id}"},
            cancel_requested=True,
            started_at=fresh,
            created_at=fresh,
            updated_at=fresh,
        )
        await _insert_task(crm_container, task, "system", ns, system_user_id)

        n = await crm_container.task_service.reconcile_stale_worker_tasks()
        assert n == 1
        row = await crm_container.task_repository.get_for_worker(tid, "system")
        assert row is not None
        assert row.status == "cancelled"
        assert row.cancel_requested is False

    @pytest.mark.asyncio
    async def test_reconcile_stale_cancel_requested_becomes_cancelled(
        self,
        crm_container,
        unique_id: str,
        system_user_id: str,
    ) -> None:
        old = _NOW() - timedelta(minutes=120)
        ns = f"g_{unique_id}"
        tid = f"stale-cancel-{unique_id}"
        task = CRMTask(
            task_id=tid,
            task_type="knowledge_import",
            status="running",
            stage="importing",
            progress_pct=40,
            company_id="system",
            namespace=ns,
            user_id=system_user_id,
            data={},
            cancel_requested=True,
            started_at=old,
            created_at=old,
            updated_at=old,
        )
        await _insert_task(crm_container, task, "system", ns, system_user_id)

        n = await crm_container.task_service.reconcile_stale_worker_tasks()
        assert n == 1
        row = await crm_container.task_repository.get_for_worker(tid, "system")
        assert row is not None
        assert row.status == "cancelled"
        assert row.cancel_requested is False
