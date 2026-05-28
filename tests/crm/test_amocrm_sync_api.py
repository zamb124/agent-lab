"""AmoCRM: фоновый импорт через POST sync / custom_fields (контракт HTTP без проверки воркера)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm.container import CRMContainer
from apps.crm.db.models import CRMTask
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from tests.crm.e2e._json_helpers import json_object, object_dict, object_str

pytestmark = pytest.mark.timeout(30, func_only=True)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


async def _insert_task(
    crm_container: CRMContainer,
    task: CRMTask,
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
        _ = await crm_container.task_repository.create(task)
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_amocrm_sync_returns_202(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/sync",
        headers=auth_headers_system,
    )
    assert resp.status_code == 202, resp.text
    data = _http_json(resp)
    assert data.get("task_type") == "namespace_integration_job"
    assert data.get("namespace") == ns
    task_id = object_str(data.get("task_id"), field="task_id")
    assert len(task_id) > 0
    status = data.get("status")
    assert status in ("pending", "running")


@pytest.mark.asyncio
async def test_amocrm_custom_fields_sync_returns_202(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    resp = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/integrations/amocrm/custom_fields/sync",
        headers=auth_headers_system,
    )
    assert resp.status_code == 202, resp.text
    data = _http_json(resp)
    assert data.get("task_type") == "namespace_integration_job"
    assert data.get("namespace") == ns
    task_id = object_str(data.get("task_id"), field="task_id")
    assert len(task_id) > 0


@pytest.mark.asyncio
async def test_amocrm_sync_active_conflict(
    crm_client: AsyncClient,
    crm_container: CRMContainer,
    auth_headers_system: dict[str, str],
    unique_id: str,
    system_user_id: str,
) -> None:
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
    conflict_body = _http_json(resp)
    detail = object_dict(conflict_body["detail"], field="detail")
    assert detail["code"] == "active_task_exists"
    assert detail["task_type"] == "namespace_integration_job"
    assert detail.get("dedup") == {"provider_id": "amocrm", "job": "entities"}
