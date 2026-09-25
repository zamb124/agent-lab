"""CrmClient against ASGI CRM service."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from core.clients.crm_client import CrmClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User

pytestmark = [pytest.mark.asyncio]


@contextmanager
def _namespace_context(*, user: User, company: Company, namespace: str, auth_token: str) -> Iterator[None]:
    previous = get_context()
    ctx = build_job_context(
        company=company,
        user=user,
        host="",
        trace_id="crm-client-test",
        session_id="crm-client",
        channel="test",
    )
    set_context(
        ctx.model_copy(
            update={
                "active_namespace": namespace,
                "auth_token": auth_token,
            }
        )
    )
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


async def test_crm_client_create_note_and_get_entity(
    crm_client,
    frontend_di,
    auth_token_system: str,
    unique_id: str,
) -> None:
    _ = crm_client
    company = await Company.get("system")
    assert company is not None
    user = await User.get("system")
    assert user is not None
    namespace = "default"

    with _namespace_context(
        user=user,
        company=company,
        namespace=namespace,
        auth_token=auth_token_system,
    ):
        client = CrmClient()
        created = await client.create_note(
            name=f"CrmClient note {unique_id}",
            description=f"Body for client test {unique_id}",
            namespace=namespace,
        )
        entity_id = created.get("entity_id")
        assert isinstance(entity_id, str) and entity_id.strip()

        got = await client.get_entity(entity_id)
        entity = got.get("entity")
        assert isinstance(entity, dict)
        assert entity.get("entity_id") == entity_id
        assert entity.get("name") == f"CrmClient note {unique_id}"

        listed = await client.list_notes(
            date_from="1970-01-01",
            date_to="2099-12-31",
            namespace=namespace,
            limit=50,
        )
        items = listed.get("items")
        assert isinstance(items, list)
        assert any(
            isinstance(row, dict) and row.get("entity_id") == entity_id for row in items
        )


async def test_crm_client_search_entities(
    crm_client,
    frontend_di,
    auth_token_system: str,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    from tests.fixtures.crm_test_setup import wait_for_crm_semantic_search_hit

    company = await Company.get("system")
    assert company is not None
    user = await User.get("system")
    assert user is not None

    marker = f"crm_client_search_{unique_id}"
    create = await crm_client.post(
        "/crm/api/v1/entities",
        json={
            "entity_type": "organization",
            "name": f"Org {unique_id}",
            "description": f"Desc {marker} " + ("context " * 40),
            "namespace": "default",
        },
        headers=auth_headers_system,
    )
    assert create.status_code in (200, 201), create.text

    await wait_for_crm_semantic_search_hit(
        crm_client,
        auth_headers_system,
        query=marker,
        entity_type="organization",
        namespace="default",
    )

    with _namespace_context(
        user=user,
        company=company,
        namespace="default",
        auth_token=auth_token_system,
    ):
        result = await CrmClient().search_entities(
            query=marker,
            entity_type="organization",
            namespace="default",
            limit=5,
        )
        hits = result.get("hits")
        assert isinstance(hits, list) and len(hits) >= 1
        assert hits[0].get("entity_id")
