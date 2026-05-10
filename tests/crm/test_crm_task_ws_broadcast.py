"""Публикация доменного UI-события crm/task/updated."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.crm.db.models import CRMTask
from apps.crm.services import crm_task_ws_broadcast as broadcast_mod


@pytest.mark.asyncio
async def test_broadcast_crm_task_updated_for_user_payload(monkeypatch):
    recorded: list[tuple[str, str, dict]] = []

    async def _capture(**kwargs: object) -> None:
        user_id = kwargs.get('user_id')
        event_type = kwargs.get('type')
        payload = kwargs.get('payload')
        if not isinstance(user_id, str) or not isinstance(event_type, str) or not isinstance(payload, dict):
            raise AssertionError('publish_ui_event_to_user mock: expected user_id, type, payload')
        recorded.append((user_id, event_type, payload))

    monkeypatch.setattr(broadcast_mod, "publish_ui_event_to_user", _capture)

    row = CRMTask(
        task_id="task_ws_test_1",
        task_type="note_analyze",
        status="running",
        stage="reading_attachments",
        progress_pct=15,
        error_message=None,
        data={"note_id": "note_1"},
        taskiq_task_id=None,
        cancel_requested=False,
        company_id="company_1",
        namespace="default",
        user_id="user_1",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    await broadcast_mod.broadcast_crm_task_updated_for_user(user_id="user_1", row=row)

    assert len(recorded) == 1
    uid, event_type, payload = recorded[0]
    assert uid == "user_1"
    assert event_type == "crm/task/updated"
    task = payload["task"]
    assert task["task_id"] == "task_ws_test_1"
    assert task["task_type"] == "note_analyze"
    assert task["status"] == "running"
    assert task["data"]["note_id"] == "note_1"
