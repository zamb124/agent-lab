"""OpenFGA flow/group permission matrix."""

from __future__ import annotations

import pytest

from apps.flows.src.models import Edge, FlowConfig
from apps.flows.src.services.flow_access_service import FlowAccessService
from core.authz.company_sync import sync_company_member_roles
from core.authz.errors import AuthzDenied
from core.authz.group_sync import sync_user_groups
from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation


@pytest.mark.asyncio
async def test_platform_admin_views_restricted_flow_via_fga(container, unique_id) -> None:
    authz = container.authz_service
    access = FlowAccessService(authz)
    admin_id = f"admin_{unique_id}"
    owner_id = f"owner_{unique_id}"
    flow_id = f"flow_{unique_id}"
    company_id = f"co_{unique_id}"
    await sync_user_groups(
        authz,
        user_id=admin_id,
        groups=["admin"],
        company_ids=[],
        previous_groups=[],
    )
    config = FlowConfig(
        flow_id=flow_id,
        name="restricted",
        entry="main",
        permission=["secret-group"],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await access.sync_flow_saved(
        config, company_id=company_id, owner_user_id=owner_id
    )
    await authz.require_can_view(AuthzObject.flow(flow_id), user_id=admin_id)
    await authz.require_can_edit(AuthzObject.flow(flow_id), user_id=admin_id)
    with pytest.raises(AuthzDenied):
        await authz.require_relation(
            AuthzRelation.CAN_SHARE,
            AuthzObject.flow(flow_id),
            user_id=admin_id,
        )


@pytest.mark.asyncio
async def test_group_viewer_can_view_flow(container, unique_id) -> None:
    authz = container.authz_service
    access = FlowAccessService(authz)
    user_id = f"mgr_{unique_id}"
    flow_id = f"flow_{unique_id}"
    company_id = f"co_{unique_id}"
    await sync_user_groups(
        authz,
        user_id=user_id,
        groups=["managers"],
        company_ids=[company_id],
        previous_groups=[],
    )
    config = FlowConfig(
        flow_id=flow_id,
        name="perm",
        entry="main",
        permission=["managers"],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await access.sync_flow_saved(
        config, company_id=company_id, owner_user_id=f"owner_{unique_id}"
    )
    await authz.require_can_view(AuthzObject.flow(flow_id), user_id=user_id)
    with pytest.raises(AuthzDenied):
        await authz.require_can_view(
            AuthzObject.flow(flow_id), user_id=f"stranger_{unique_id}"
        )


@pytest.mark.asyncio
async def test_cross_company_group_does_not_view_foreign_flow(
    container, unique_id
) -> None:
    authz = container.authz_service
    access = FlowAccessService(authz)
    company_a = f"co_a_{unique_id}"
    company_b = f"co_b_{unique_id}"
    member_a = f"dev_a_{unique_id}"
    member_b = f"dev_b_{unique_id}"
    flow_id = f"flow_{unique_id}"
    await sync_user_groups(
        authz,
        user_id=member_a,
        groups=["developers"],
        company_ids=[company_a],
        previous_groups=[],
    )
    await sync_user_groups(
        authz,
        user_id=member_b,
        groups=["developers"],
        company_ids=[company_b],
        previous_groups=[],
    )
    config = FlowConfig(
        flow_id=flow_id,
        name="restricted",
        entry="main",
        permission=["developers"],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await access.sync_flow_saved(
        config, company_id=company_a, owner_user_id=f"owner_{unique_id}"
    )
    admin_id = f"admin_{unique_id}"
    await sync_user_groups(
        authz,
        user_id=admin_id,
        groups=["admin"],
        company_ids=[],
        previous_groups=[],
    )
    await authz.require_can_view(AuthzObject.flow(flow_id), user_id=member_a)
    with pytest.raises(AuthzDenied):
        await authz.require_can_view(AuthzObject.flow(flow_id), user_id=member_b)
    await authz.require_can_view(AuthzObject.flow(flow_id), user_id=admin_id)


@pytest.mark.asyncio
async def test_empty_permission_company_visible(container, unique_id) -> None:
    access = FlowAccessService(container.authz_service)
    flow_id = f"flow_{unique_id}"
    company_id = f"co_{unique_id}"
    member_id = f"member_{unique_id}"
    await sync_company_member_roles(
        container.authz_service,
        company_id=company_id,
        user_id=member_id,
        roles=["member"],
    )
    config = FlowConfig(
        flow_id=flow_id,
        name="public",
        entry="main",
        permission=[],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await access.sync_flow_saved(
        config, company_id=company_id, owner_user_id=f"owner_{unique_id}"
    )
    assert await container.authz_service.can_view(
        AuthzObject.flow(flow_id), user_id=member_id
    )


@pytest.mark.asyncio
async def test_sync_flow_saved_admin_group_is_unscoped(container, unique_id) -> None:
    authz = container.authz_service
    access = FlowAccessService(authz)
    flow_id = f"flow_{unique_id}"
    company_id = f"co_{unique_id}"
    config = FlowConfig(
        flow_id=flow_id,
        name="demo",
        entry="main",
        permission=["admin", "developers"],
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state): return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
    )
    await access.sync_flow_saved(
        config, company_id=company_id, owner_user_id=f"owner_{unique_id}"
    )
    subjects = {item.subject.fga_user for item in await authz.list_tuples(AuthzObject.flow(flow_id))}
    assert "group:admin#member" in subjects
    assert f"group:{company_id}/developers#member" in subjects
