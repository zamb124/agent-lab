"""CRM note-analyze HTTP Check goes through AuthzDenied, not AccessService."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from core.authz.models import AuthzObject

pytestmark = pytest.mark.asyncio


async def test_note_analyze_without_can_edit_returns_403(
    crm_client: AsyncClient,
    crm_container,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    ns = f"g_{unique_id}"
    note_resp = await crm_client.post(
        "/crm/api/v1/entities/",
        json={
            "entity_type": "note",
            "name": f"Authz note {unique_id}",
            "namespace": ns,
        },
        headers=auth_headers_system,
    )
    assert note_resp.status_code in (200, 201), note_resp.text
    note_id = note_resp.json()["entity_id"]
    leftover = await crm_container.authz_service.list_tuples(
        AuthzObject.crm_entity(note_id)
    )
    if leftover:
        await crm_container.authz_service.delete(leftover)

    resp = await crm_client.post(
        "/crm/api/v1/tasks/note-analyze",
        json={"note_id": note_id},
        headers=auth_headers_system,
    )
    assert resp.status_code == 403, resp.text
