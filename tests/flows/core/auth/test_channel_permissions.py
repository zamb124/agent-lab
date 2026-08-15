"""Channel-level OpenFGA permissions."""

from __future__ import annotations

import pytest

from apps.flows.src.channels.base import PermissionDenied
from core.authz.group_sync import sync_user_groups


@pytest.mark.asyncio
async def test_flow_permission_denied_no_groups(
    container, flow_with_permission
) -> None:
    channel = container.get_channel("a2a", flow_with_permission)
    with pytest.raises(PermissionDenied):
        await channel.check_permissions("user_none", branch_id="default")


@pytest.mark.asyncio
async def test_flow_permission_denied_wrong_group(
    container, flow_with_permission, unique_id
) -> None:
    user_id = f"wrong_{unique_id}"
    await sync_user_groups(
        container.authz_service,
        user_id=user_id,
        groups=["users", "guests"],
        company_ids=[f"perm_co_{unique_id}"],
        previous_groups=[],
    )
    channel = container.get_channel("a2a", flow_with_permission)
    with pytest.raises(PermissionDenied):
        await channel.check_permissions(user_id, branch_id="default")


@pytest.mark.asyncio
async def test_flow_permission_granted_correct_group(
    container, flow_with_permission, unique_id
) -> None:
    user_id = f"mgr_{unique_id}"
    await sync_user_groups(
        container.authz_service,
        user_id=user_id,
        groups=["managers"],
        company_ids=[f"perm_co_{unique_id}"],
        previous_groups=[],
    )
    channel = container.get_channel("a2a", flow_with_permission)
    await channel.check_permissions(user_id, branch_id="default")


@pytest.mark.asyncio
async def test_flow_permission_granted_admin(
    container, flow_with_permission, unique_id
) -> None:
    user_id = f"admin_{unique_id}"
    await sync_user_groups(
        container.authz_service,
        user_id=user_id,
        groups=["admin"],
        company_ids=[],
        previous_groups=[],
    )
    channel = container.get_channel("a2a", flow_with_permission)
    await channel.check_permissions(user_id, branch_id="default")


@pytest.mark.asyncio
async def test_skill_permission_inherits_flow_viewer(
    container, flow_with_skill_permission, unique_id
) -> None:
    """FGA: viewer from flow → branch can_view (branch permission only adds access)."""
    user_id = f"users_{unique_id}"
    await sync_user_groups(
        container.authz_service,
        user_id=user_id,
        groups=["users"],
        company_ids=[f"skill_co_{unique_id}"],
        previous_groups=[],
    )
    channel = container.get_channel("a2a", flow_with_skill_permission)
    await channel.check_permissions(user_id, branch_id="vip")


@pytest.mark.asyncio
async def test_skill_permission_granted(
    container, flow_with_skill_permission, unique_id
) -> None:
    user_id = f"vip_{unique_id}"
    await sync_user_groups(
        container.authz_service,
        user_id=user_id,
        groups=["vip"],
        company_ids=[f"skill_co_{unique_id}"],
        previous_groups=[],
    )
    channel = container.get_channel("a2a", flow_with_skill_permission)
    await channel.check_permissions(user_id, branch_id="vip")


@pytest.mark.asyncio
async def test_default_skill_uses_flow_permission(
    container, flow_with_skill_permission, unique_id
) -> None:
    user_id = f"users_{unique_id}"
    await sync_user_groups(
        container.authz_service,
        user_id=user_id,
        groups=["users"],
        company_ids=[f"skill_co_{unique_id}"],
        previous_groups=[],
    )
    channel = container.get_channel("a2a", flow_with_skill_permission)
    await channel.check_permissions(user_id, branch_id="default")
