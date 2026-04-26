"""AmoCRM: импорт задач (_import_tasks) с подменой ответа API."""

from __future__ import annotations

from datetime import date

import pytest

from apps.crm.integrations.amocrm.mapping import AMO_PROVIDER_ID
from apps.crm.integrations.amocrm.service import AmoCRMIntegrationService
from apps.crm.integrations.entity_upsert import upsert_canonical_by_external_ref
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User

pytestmark = pytest.mark.timeout(30, func_only=True)


@pytest.mark.asyncio
async def test_amocrm_import_tasks_upsert_and_relationships(
    crm_container,
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = f"amo_task_{unique_id}"
    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        await upsert_canonical_by_external_ref(
            entity_repo=crm_container.entity_repository,
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            entity_type="lead",
            source_id=AMO_PROVIDER_ID,
            record_id="555",
            name="Lead for tasks",
            patch_attributes={},
            account_key="sub_amocrm",
        )
        await upsert_canonical_by_external_ref(
            entity_repo=crm_container.entity_repository,
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            entity_type="member",
            source_id=AMO_PROVIDER_ID,
            record_id="42",
            name="Owner user",
            patch_attributes={},
            account_key="sub_amocrm",
        )

        service = AmoCRMIntegrationService(
            oauth_service=crm_container.oauth_service,
            entity_repository=crm_container.entity_repository,
            entity_type_repository=crm_container.entity_type_repository,
            relationship_repository=crm_container.relationship_repository,
            entity_service=crm_container.entity_service,
        )

        task_payload: dict = {
            "id": 9001,
            "entity_id": 555,
            "entity_type": "leads",
            "is_completed": False,
            "task_type_id": 1,
            "text": "Позвонить\nвторая строка",
            "complete_till": 1704067200,
            "responsible_user_id": 42,
        }

        async def fake_get_json(url: str, token: str) -> dict:
            assert "/api/v4/tasks" in url
            assert isinstance(token, str)
            return {"_embedded": {"tasks": [task_payload]}, "_links": {}}

        service._get_json = fake_get_json  # type: ignore[method-assign]

        stats: dict[str, int] = {
            "relationships": 0,
            "notes": 0,
            "tasks": 0,
            "tasks_skipped_no_parent": 0,
        }
        await service._import_tasks(
            base="https://example.amocrm.ru",
            access_token="token",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            account_key="sub_amocrm",
            stats=stats,
        )
        assert stats["tasks"] == 1
        assert stats["tasks_skipped_no_parent"] == 0
        assert stats["relationships"] == 2

        rows = await crm_container.entity_repository.find_by_external_ref(
            company_id="system",
            namespace=ns,
            entity_type="task",
            source_id=AMO_PROVIDER_ID,
            record_id="9001",
        )
        assert len(rows) == 1
        ent = rows[0]
        assert ent.attributes.get("status") == "todo"
        assert ent.attributes.get("amo_task_type_id") == 1
        assert ent.attributes.get("amo_task_type_name") == "Звонок"
        assert ent.due_date == date(2024, 1, 1)
        assert ent.description is not None
        assert "Позвонить" in ent.description

        lead_rows = await crm_container.entity_repository.find_by_external_ref(
            company_id="system",
            namespace=ns,
            entity_type="lead",
            source_id=AMO_PROVIDER_ID,
            record_id="555",
        )
        member_rows = await crm_container.entity_repository.find_by_external_ref(
            company_id="system",
            namespace=ns,
            entity_type="member",
            source_id=AMO_PROVIDER_ID,
            record_id="42",
        )
        assert len(lead_rows) == 1
        assert len(member_rows) == 1
        lead_id = lead_rows[0].entity_id
        member_id = member_rows[0].entity_id

        rel_related = await crm_container.relationship_repository.find_exact(
            ent.entity_id,
            lead_id,
            "related_to",
        )
        rel_assigned = await crm_container.relationship_repository.find_exact(
            ent.entity_id,
            member_id,
            "assigned_to",
        )
        assert rel_related is not None
        assert rel_assigned is not None
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_amocrm_import_tasks_skips_unmapped_parent(
    crm_container,
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = f"amo_task_skip_{unique_id}"
    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
        service = AmoCRMIntegrationService(
            oauth_service=crm_container.oauth_service,
            entity_repository=crm_container.entity_repository,
            entity_type_repository=crm_container.entity_type_repository,
            relationship_repository=crm_container.relationship_repository,
            entity_service=crm_container.entity_service,
        )

        task_payload: dict = {
            "id": 9101,
            "entity_id": 1,
            "entity_type": "customers",
            "is_completed": False,
            "text": "orphan",
        }

        async def fake_get_json(url: str, token: str) -> dict:
            return {"_embedded": {"tasks": [task_payload]}, "_links": {}}

        service._get_json = fake_get_json  # type: ignore[method-assign]

        stats: dict[str, int] = {
            "relationships": 0,
            "notes": 0,
            "tasks": 0,
            "tasks_skipped_no_parent": 0,
        }
        await service._import_tasks(
            base="https://example.amocrm.ru",
            access_token="token",
            namespace=ns,
            company_id="system",
            user_id=system_user_id,
            account_key="sub_amocrm",
            stats=stats,
        )
        assert stats["tasks"] == 0
        assert stats["tasks_skipped_no_parent"] == 1
    finally:
        clear_context()
