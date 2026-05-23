"""GET /namespaces/{namespace}/suggests и POST для разрешения."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from apps.crm.db.models import CRMEntity, CRMSuggest
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User

pytestmark = pytest.mark.timeout(20, func_only=True)


@pytest.mark.asyncio
async def test_suggests_list_empty(
    crm_client: AsyncClient,
    auth_headers_system: dict,
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    response = await crm_client.get(
        f"/crm/api/v1/namespaces/{ns}/suggests",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_suggests_lifecycle(
    crm_client: AsyncClient,
    crm_container,
    auth_headers_system: dict,
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = "default"  # Используем namespace default, потому что он обычно существует и доступен

    survivor_id = f"surv_{unique_id}"
    source_id = f"src_{unique_id}"
    suggest_id = f"sug_{unique_id}"

    # Настраиваем контекст
    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        # Создаём сущности для merge
        survivor = CRMEntity(
            entity_id=survivor_id,
            company_id="system",
            namespace=ns,
            entity_type="contact",
            name="Survivor",
            search_vector="",
            user_id=system_user_id,
        )
        source = CRMEntity(
            entity_id=source_id,
            company_id="system",
            namespace=ns,
            entity_type="contact",
            name="Source",
            search_vector="",
            user_id=system_user_id,
        )
        await crm_container.entity_repository.create(survivor)
        await crm_container.entity_repository.create(source)

        # Создаём suggest
        now = datetime.now(timezone.utc)
        suggest = CRMSuggest(
            suggest_id=suggest_id,
            company_id="system",
            namespace=ns,
            suggest_type="duplicate",
            status="pending",
            target_entity_ids=[survivor_id, source_id],
            payload={
                "survivor_entity_id": survivor_id,
                "source_entity_id": source_id,
                "scalar_choices": {"name": "survivor"},
                "attribute_choices": {},
            },
            created_at=now,
            updated_at=now,
        )
        await crm_container.suggest_repository.create(suggest)
    finally:
        clear_context()

    # 1. List suggests
    response = await crm_client.get(
        f"/crm/api/v1/namespaces/{ns}/suggests",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    found = [item for item in data["items"] if item["suggest_id"] == suggest_id]
    assert len(found) == 1
    assert found[0]["status"] == "pending"

    # 2. Resolve Suggest
    response = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/suggests/{suggest_id}/resolve",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"

    # Проверяем, что сущность смержена (source должен быть удалён)
    set_context(ctx)
    try:
        source_check = await crm_container.entity_repository.get(source_id)
        assert source_check is None
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_suggests_dismiss(
    crm_client: AsyncClient,
    crm_container,
    auth_headers_system: dict,
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = "default"
    suggest_id = f"sug_{unique_id}_2"

    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        now = datetime.now(timezone.utc)
        suggest = CRMSuggest(
            suggest_id=suggest_id,
            company_id="system",
            namespace=ns,
            suggest_type="missed_entity",
            status="pending",
            target_entity_ids=["fake"],
            payload={},
            created_at=now,
            updated_at=now,
        )
        await crm_container.suggest_repository.create(suggest)
    finally:
        clear_context()

    # Dismiss Suggest
    response = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/suggests/{suggest_id}/dismiss",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "dismissed"

    # Проверяем, что записи больше нет в pending-списке
    response = await crm_client.get(
        f"/crm/api/v1/namespaces/{ns}/suggests",
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    data = response.json()
    assert not any(item["suggest_id"] == suggest_id for item in data["items"])


@pytest.mark.asyncio
async def test_missed_entity_dismissed_same_draft_is_not_recreated(
    crm_container,
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = f"g_{unique_id}"
    note_id = f"note_suggest_{unique_id}"

    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        note = CRMEntity(
            entity_id=note_id,
            company_id="system",
            namespace=ns,
            entity_type="note",
            name="Note with unapplied draft",
            description="Draft was analyzed but not applied yet.",
            search_vector="",
            user_id=system_user_id,
            attributes={"ai_analysis_draft": {"draft_version": 1}},
        )
        await crm_container.entity_repository.create(note)

        summary = await crm_container.suggest_service.generate_namespace_suggests(
            company_id="system",
            namespace=ns,
        )
        assert summary["missed_entity_created"] == 1

        page = await crm_container.suggest_service.list_suggests(ns, status="pending")
        created = next(
            item
            for item in page.items
            if item.suggest_type == "missed_entity"
            and item.target_entity_ids == [note_id]
        )
        await crm_container.suggest_service.dismiss_suggest(created.suggest_id, namespace=ns)

        second_summary = await crm_container.suggest_service.generate_namespace_suggests(
            company_id="system",
            namespace=ns,
        )
        assert second_summary["missed_entity_created"] == 0

        pending_page = await crm_container.suggest_service.list_suggests(ns, status="pending")
        assert not any(
            item.suggest_type == "missed_entity"
            and item.target_entity_ids == [note_id]
            for item in pending_page.items
        )

        all_page = await crm_container.suggest_service.list_suggests(ns, status=None)
        dismissed = [
            item
            for item in all_page.items
            if item.suggest_type == "missed_entity"
            and item.target_entity_ids == [note_id]
            and item.status == "dismissed"
        ]
        assert [item.suggest_id for item in dismissed] == [created.suggest_id]
    finally:
        clear_context()
