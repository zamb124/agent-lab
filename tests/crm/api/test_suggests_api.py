"""GET /namespaces/{namespace}/suggests и POST для разрешения."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import pytest
from httpx import AsyncClient, Response

from apps.crm.container import CRMContainer
from apps.crm.db.models import CRMEntity, CRMSuggest
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User
from tests.crm.e2e._json_helpers import json_object, object_list, object_str

pytestmark = pytest.mark.timeout(20, func_only=True)


def _http_json(response: Response) -> dict[str, object]:
    return json_object(cast(object, response.json()))


def _suggest_items(body: dict[str, object]) -> list[dict[str, object]]:
    return object_list(body.get("items"))


def _suggest_id_from_row(row: dict[str, object]) -> str:
    return object_str(row.get("suggest_id"), field="suggest_id")


@pytest.mark.asyncio
async def test_suggests_list_empty(
    crm_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    response = await crm_client.get(
        f"/crm/api/v1/namespaces/{ns}/suggests",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    body = _http_json(response)
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_suggests_lifecycle(
    crm_client: AsyncClient,
    crm_container: CRMContainer,
    auth_headers_system: dict[str, str],
    unique_id: str,
    system_user_id: str,
) -> None:
    ns = "default"

    survivor_id = f"surv_{unique_id}"
    source_id = f"src_{unique_id}"
    suggest_id = f"sug_{unique_id}"

    ctx = Context(
        user=User(user_id=system_user_id, name="Test"),
        active_company=Company(company_id="system", name="System"),
        channel="test",
        active_namespace=ns,
    )
    set_context(ctx)
    try:
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
        _ = await crm_container.entity_repository.create(survivor)
        _ = await crm_container.entity_repository.create(source)

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
        _ = await crm_container.suggest_repository.create(suggest)
    finally:
        clear_context()

    response = await crm_client.get(
        f"/crm/api/v1/namespaces/{ns}/suggests",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    data = _http_json(response)
    total = data.get("total")
    assert isinstance(total, int) and total >= 1
    found = [
        item
        for item in _suggest_items(data)
        if _suggest_id_from_row(item) == suggest_id
    ]
    assert len(found) == 1
    assert found[0]["status"] == "pending"

    resolve_response = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/suggests/{suggest_id}/resolve",
        headers=auth_headers_system,
    )
    assert resolve_response.status_code == 200, resolve_response.text
    resolve_body = _http_json(resolve_response)
    assert resolve_body["status"] == "resolved"

    set_context(ctx)
    try:
        source_check = await crm_container.entity_repository.get(source_id)
        assert source_check is None
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_suggests_dismiss(
    crm_client: AsyncClient,
    crm_container: CRMContainer,
    auth_headers_system: dict[str, str],
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
        _ = await crm_container.suggest_repository.create(suggest)
    finally:
        clear_context()

    dismiss_response = await crm_client.post(
        f"/crm/api/v1/namespaces/{ns}/suggests/{suggest_id}/dismiss",
        headers=auth_headers_system,
    )
    assert dismiss_response.status_code == 200, dismiss_response.text
    dismiss_body = _http_json(dismiss_response)
    assert dismiss_body["status"] == "dismissed"

    list_response = await crm_client.get(
        f"/crm/api/v1/namespaces/{ns}/suggests",
        headers=auth_headers_system,
    )
    assert list_response.status_code == 200
    list_body = _http_json(list_response)
    assert not any(
        _suggest_id_from_row(item) == suggest_id for item in _suggest_items(list_body)
    )


@pytest.mark.asyncio
async def test_missed_entity_dismissed_same_draft_is_not_recreated(
    crm_container: CRMContainer,
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
        _ = await crm_container.entity_repository.create(note)

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
        _ = await crm_container.suggest_service.dismiss_suggest(
            created.suggest_id,
            namespace=ns,
        )

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
