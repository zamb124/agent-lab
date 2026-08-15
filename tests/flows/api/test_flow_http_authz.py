"""HTTP Flows list/get/mutate gated by AuthzService."""

from __future__ import annotations

import pytest

from apps.flows.src.models import Edge, FlowConfig
from core.authz.group_sync import sync_user_groups
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


async def test_restricted_flow_hidden_from_member_without_group(
    client,
    container,
    unique_id: str,
    system_user_id: str,
    system_user2_id: str,
    auth_headers_system_user2: dict[str, str],
) -> None:
    flow_id = f"http_authz_{unique_id}"
    group_name = f"http-authz-mgrs-{unique_id}"
    config = FlowConfig(
        flow_id=flow_id,
        name="Restricted",
        entry="main",
        permission=[group_name],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    set_context(
        Context(
            user=User(user_id=system_user_id, name="System"),
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        _ = await container.flow_repository.set(config)
        await container.flow_access_service.sync_flow_saved(
            config, company_id="system", owner_user_id=system_user_id
        )
    finally:
        clear_context()

    listed = await client.get(
        "/flows/api/v1/flows/", headers=auth_headers_system_user2
    )
    assert listed.status_code == 200, listed.text
    ids = {item["flow_id"] for item in listed.json()["items"]}
    assert flow_id not in ids

    denied = await client.get(
        f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system_user2
    )
    assert denied.status_code == 403

    await sync_user_groups(
        container.authz_service,
        user_id=system_user2_id,
        groups=[group_name],
        company_ids=["system"],
        previous_groups=[],
    )
    listed_ok = await client.get(
        "/flows/api/v1/flows/", headers=auth_headers_system_user2
    )
    assert listed_ok.status_code == 200, listed_ok.text
    assert flow_id in {item["flow_id"] for item in listed_ok.json()["items"]}

    got = await client.get(
        f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system_user2
    )
    assert got.status_code == 200, got.text

    mutate = await client.patch(
        f"/flows/api/v1/flows/{flow_id}/metadata",
        headers=auth_headers_system_user2,
        json={"sticky_notes": []},
    )
    assert mutate.status_code == 403

    await container.flow_access_service.sync_flow_deleted(
        flow_id, company_id="system", branch_ids=[]
    )
    set_context(
        Context(
            user=User(user_id=system_user_id, name="System"),
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        _ = await container.flow_repository.delete(flow_id)
    finally:
        clear_context()


async def test_restricted_flow_visible_to_platform_admin_via_fga(
    client,
    container,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
    auth_headers_system_user2: dict[str, str],
) -> None:
    flow_id = f"http_authz_admin_{unique_id}"
    group_name = f"http-authz-secret-{unique_id}"
    config = FlowConfig(
        flow_id=flow_id,
        name="Restricted admin",
        entry="main",
        permission=[group_name],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    set_context(
        Context(
            user=User(user_id=system_user_id, name="System"),
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        _ = await container.flow_repository.set(config)
        await container.flow_access_service.sync_flow_saved(
            config, company_id="system", owner_user_id=f"owner_{unique_id}"
        )
    finally:
        clear_context()

    denied = await client.get(
        f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system_user2
    )
    assert denied.status_code == 403

    listed_member = await client.get(
        "/flows/api/v1/flows/", headers=auth_headers_system_user2
    )
    assert listed_member.status_code == 200, listed_member.text
    assert flow_id not in {item["flow_id"] for item in listed_member.json()["items"]}

    got = await client.get(
        f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system
    )
    assert got.status_code == 200, got.text

    listed_admin = await client.get(
        "/flows/api/v1/flows/", headers=auth_headers_system
    )
    assert listed_admin.status_code == 200, listed_admin.text
    assert flow_id in {item["flow_id"] for item in listed_admin.json()["items"]}

    await container.flow_access_service.sync_flow_deleted(
        flow_id, company_id="system", branch_ids=[]
    )
    set_context(
        Context(
            user=User(user_id=system_user_id, name="System"),
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        _ = await container.flow_repository.delete(flow_id)
    finally:
        clear_context()

