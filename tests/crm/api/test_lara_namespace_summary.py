"""GET /namespaces/lara-summary для метаданных Lara."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from apps.crm.db.models import CRMTask
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User

pytestmark = pytest.mark.timeout(20, func_only=True)


@pytest.mark.asyncio
async def test_lara_namespace_summary_zeros(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    response = await crm_client.get(
        "/crm/api/v1/namespaces/lara-summary",
        params={"namespace": ns},
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["namespace"] == ns
    assert body["knowledge_imports_awaiting_review"] == 0
    assert body["knowledge_imports_in_progress"] == 0
    assert body["notes_with_analysis_draft_not_applied"] == 0


@pytest.mark.asyncio
async def test_lara_namespace_summary_import_awaiting_review(
    crm_client: AsyncClient,
    crm_container,
    auth_headers_system: dict[str, str],
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = f"g_{unique_id}"
    task_id = f"ki_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    row = CRMTask(
        task_id=task_id,
        task_type="knowledge_import",
        status="completed",
        stage="completed",
        progress_pct=100,
        company_id="system",
        namespace=ns,
        user_id=system_user_id,
        data={
            "mode": "notes_only",
            "notes_created_count": 1,
            "entities_created_count": 0,
            "relationships_created_count": 0,
            "created_entity_ids": ["fake-entity-id"],
            "created_relationship_ids": [],
            "attachment_document_ids": [],
            "review_completed_at": None,
            "chunk_errors": [],
        },
        completed_at=now,
        created_at=now,
        updated_at=now,
    )
    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        await crm_container.task_repository.create(row)
    finally:
        clear_context()

    response = await crm_client.get(
        "/crm/api/v1/namespaces/lara-summary",
        params={"namespace": ns},
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    assert response.json()["knowledge_imports_awaiting_review"] == 1


@pytest.mark.asyncio
async def test_lara_namespace_summary_note_draft_not_applied(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    create_ns = await crm_client.post(
        "/crm/api/v1/namespaces",
        json={
            "name": ns,
            "template_id": "sales",
        },
        headers=auth_headers_system,
    )
    assert create_ns.status_code in (201, 409), create_ns.text

    editability_resp = await crm_client.get(
        f"/crm/api/v1/namespaces/{ns}/editability",
        headers=auth_headers_system,
    )
    assert editability_resp.status_code == 200, editability_resp.text
    current_allowed = editability_resp.json().get("current_allowed_type_ids") or []
    target_allowed = sorted({*current_allowed, "note"})
    update_ns = await crm_client.put(
        f"/crm/api/v1/namespaces/{ns}",
        json={"allowed_type_ids": target_allowed},
        headers=auth_headers_system,
    )
    assert update_ns.status_code == 200, update_ns.text

    create = await crm_client.post(
        "/crm/api/v1/entities/",
        json={
            "entity_type": "note",
            "namespace": ns,
            "name": f"Lara summary note {unique_id}",
            "description": "body",
        },
        headers=auth_headers_system,
    )
    assert create.status_code in (200, 201), create.text
    entity_id = create.json()["entity_id"]

    get_ent = await crm_client.get(
        f"/crm/api/v1/entities/{entity_id}",
        headers=auth_headers_system,
    )
    assert get_ent.status_code == 200, get_ent.text
    prev_attrs = dict(get_ent.json().get("attributes") or {})
    prev_attrs["ai_analysis_draft"] = {"draft_version": 1, "entities": []}

    put = await crm_client.put(
        f"/crm/api/v1/entities/{entity_id}",
        json={"attributes": prev_attrs},
        headers=auth_headers_system,
    )
    assert put.status_code == 200, put.text

    response = await crm_client.get(
        "/crm/api/v1/namespaces/lara-summary",
        params={"namespace": ns},
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    assert response.json()["notes_with_analysis_draft_not_applied"] == 1
