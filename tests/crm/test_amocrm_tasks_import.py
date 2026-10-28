"""AmoCRM: импорт задач (_import_tasks) с подменой ответа API."""

from __future__ import annotations

from datetime import date

import pytest

from apps.crm.integrations.amocrm.mapping import AMO_PROVIDER_ID
from apps.crm.integrations.amocrm.service import AmoCRMIntegrationService
from apps.crm.integrations.entity_upsert import upsert_canonical_by_external_ref
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.relationship import Relationship
from core.context import clear_context, set_context
from core.identity.integration_external_author import IntegrationExternalAuthorService
from core.identity.system_bootstrap import ensure_system_company_exists
from core.models.context_models import Context
from core.models.identity_models import Company, NamespaceKind, User
from core.rag.constants import RAG_IN_PROCESS_PROVIDER_ID
from core.rag.factory import get_rag_provider
from core.worktracker.models import WorkItem, WorkItemState

pytestmark = pytest.mark.timeout(30, func_only=True)


def _test_shared_storage():
    from apps.crm.config import get_crm_settings
    from core.context import get_context
    from core.db.storage import SharedStorage, Storage

    shared_url = get_crm_settings().database.shared_url
    if shared_url is None or shared_url == "":
        raise ValueError("database.shared_url is required")
    return SharedStorage(Storage(db_url=shared_url, get_context_func=get_context))


@pytest.mark.asyncio
async def test_amocrm_import_tasks_upsert_and_relationships(
    crm_di,
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
        await ensure_system_company_exists(
        )
        _ = await crm_di.namespace_service.get_or_create(
            ns,
            description="amo tasks",
            kind=NamespaceKind.COMPANY_WORKSPACE,
        )
        _, _ = await upsert_canonical_by_external_ref(
            rag=get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
            entity_access=crm_di.crm_entity_access_service,
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
        _, _ = await upsert_canonical_by_external_ref(
            rag=get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
            entity_access=crm_di.crm_entity_access_service,
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
            oauth_service=crm_di.oauth_service,
            rag=get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
            entity_service=crm_di.entity_service,
            namespace_service=crm_di.namespace_service,
            task_service=crm_di.task_service,
            integration_external_author=IntegrationExternalAuthorService(
                storage=_test_shared_storage(),
                authz=crm_di.authz_service,
            ),
            entity_access=crm_di.crm_entity_access_service,
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
            "created_by": 42,
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
            account_key="sub_amocrm",
            stats=stats,
            sync_user_id=system_user_id,
        )
        assert stats["tasks"] == 1
        assert stats["tasks_skipped_no_parent"] == 0
        assert stats["relationships"] == 2

        rows = await CRMEntity.list_by_namespace_entity_type_and_external_ref(
            company_id="system",
            namespace=ns,
            entity_type="task",
            source_id=AMO_PROVIDER_ID,
            record_id="9001",
        )
        assert len(rows) == 1
        ent = rows[0]
        assert ent.user_id == system_user_id
        assert ent.attributes.get("amo_task_type_id") == 1
        assert ent.attributes.get("amo_task_type_name") == "Звонок"
        assert ent.description is not None
        assert "Позвонить" in ent.description

        # Канбан-статус и срок живут в парном WorkItem, не на CRM-узле.
        work_item = await WorkItem.any_crm_activity_by_entity_id(
            "system", ent.entity_id
        )
        assert work_item is not None
        assert work_item.state is WorkItemState.OPEN
        assert work_item.due_date is not None
        assert work_item.due_date.date() == date(2024, 1, 1)

        lead_rows = await CRMEntity.list_by_namespace_entity_type_and_external_ref(
            company_id="system",
            namespace=ns,
            entity_type="lead",
            source_id=AMO_PROVIDER_ID,
            record_id="555",
        )
        member_rows = await CRMEntity.list_by_namespace_entity_type_and_external_ref(
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

        rel_related = await Relationship.by_namespace_source_target_and_type(
            company_id="system",
            source_entity_id=ent.entity_id,
            target_entity_id=lead_id,
            relationship_type="related_to",
            namespace=ns,
        )
        rel_assigned = await Relationship.by_namespace_source_target_and_type(
            company_id="system",
            source_entity_id=ent.entity_id,
            target_entity_id=member_id,
            relationship_type="assigned_to",
            namespace=ns,
        )
        assert rel_related is not None
        assert rel_assigned is not None
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_amocrm_import_tasks_skips_unmapped_parent(
    crm_di,
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
            oauth_service=crm_di.oauth_service,
            rag=get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID),
            entity_service=crm_di.entity_service,
            namespace_service=crm_di.namespace_service,
            task_service=crm_di.task_service,
            integration_external_author=IntegrationExternalAuthorService(
                storage=_test_shared_storage(),
                authz=crm_di.authz_service,
            ),
            entity_access=crm_di.crm_entity_access_service,
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
            account_key="sub_amocrm",
            stats=stats,
            sync_user_id=system_user_id,
        )
        assert stats["tasks"] == 0
        assert stats["tasks_skipped_no_parent"] == 1
    finally:
        clear_context()
