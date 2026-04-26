"""AmoCRM: фоновый импорт через POST sync / custom_fields (контракт HTTP без проверки воркера)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from apps.crm.db.models import CRMTask

pytestmark = pytest.mark.timeout(30, func_only=True)


@pytest.mark.asyncio
async def test_amocrm_sync_returns_202(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/sync",
        headers=auth_headers_system,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data.get("task_type") == "namespace_integration_job"
    assert data.get("namespace") == ns
    tid = data.get("task_id")
    assert isinstance(tid, str) and len(tid) > 0
    assert data.get("status") in ("pending", "running")


@pytest.mark.asyncio
async def test_amocrm_custom_fields_sync_returns_202(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/custom_fields/sync",
        headers=auth_headers_system,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data.get("task_type") == "namespace_integration_job"
    assert data.get("namespace") == ns
    tid = data.get("task_id")
    assert isinstance(tid, str) and len(tid) > 0


@pytest.mark.asyncio
async def test_amocrm_sync_active_conflict(
    crm_client: AsyncClient,
    crm_container,
    auth_headers_system: dict,
    unique_id: str,
    system_user_id: str,
) -> None:
    from datetime import datetime, timezone

    from tests.crm.test_task_dedup_and_actions import _insert_task

    ns = f"g_{unique_id}"
    now = datetime.now(timezone.utc)
    running = CRMTask(
        task_id=f"amo-running-{unique_id}",
        task_type="namespace_integration_job",
        status="running",
        stage="leads",
        progress_pct=10,
        company_id="system",
        namespace=ns,
        user_id=system_user_id,
        data={"provider_id": "amocrm", "job": "entities", "stats": {}},
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    await _insert_task(crm_container, running, "system", ns, system_user_id)

    resp = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/sync",
        headers=auth_headers_system,
    )
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "active_task_exists"
    assert detail["task_type"] == "namespace_integration_job"
    assert detail.get("dedup") == {"provider_id": "amocrm", "job": "entities"}
