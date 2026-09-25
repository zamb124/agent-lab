"""Channel-level OpenFGA permissions."""

from __future__ import annotations

import pytest

from apps.flows.src.channels.a2a import A2AChannel
from apps.flows.src.channels.base import PermissionDenied
from apps.flows.src.channels.factory import get_channel
from core.authz.group_sync import sync_user_groups


def _a2a_channel(di, flow_id: str) -> A2AChannel:
    return get_channel(
        "a2a",
        flow_id,
        variables_service=di.variables_service,
        authz_service=di.authz_service,
        workflow_runtime=di.workflow_runtime,
        redis_client=di.redis_client,
        handoff_orchestrator_service=di.handoff_orchestrator_service,
        flow_factory=di.flow_factory,
        tool_registry=di.tool_registry,
        projection_service=di.a2a_task_projection_service,
        shared_storage=di.shared_storage,
        channel_registry=di.channel_registry,
        mail_service=di.mail_service,
        flow_ui_share_service=di.flow_ui_share_service,
        hitl_conversation_service=di.hitl_conversation_service,
        files_service=di.files_service,
    )


@pytest.mark.asyncio
async def test_flow_permission_denied_no_groups(
    di, flow_with_permission
) -> None:
    channel = _a2a_channel(di, flow_with_permission)
    with pytest.raises(PermissionDenied):
        await channel.check_permissions("user_none", branch_id="default")


@pytest.mark.asyncio
async def test_flow_permission_denied_wrong_group(
    di, flow_with_permission, unique_id
) -> None:
    user_id = f"wrong_{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["users", "guests"],
        company_ids=[f"perm_co_{unique_id}"],
        previous_groups=[],
    )
    channel = _a2a_channel(di, flow_with_permission)
    with pytest.raises(PermissionDenied):
        await channel.check_permissions(user_id, branch_id="default")


@pytest.mark.asyncio
async def test_flow_permission_granted_correct_group(
    di, flow_with_permission, unique_id
) -> None:
    user_id = f"mgr_{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["managers"],
        company_ids=[f"perm_co_{unique_id}"],
        previous_groups=[],
    )
    channel = _a2a_channel(di, flow_with_permission)
    await channel.check_permissions(user_id, branch_id="default")


@pytest.mark.asyncio
async def test_flow_permission_granted_admin(
    di, flow_with_permission, unique_id
) -> None:
    user_id = f"admin_{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["admin"],
        company_ids=[],
        previous_groups=[],
    )
    channel = _a2a_channel(di, flow_with_permission)
    await channel.check_permissions(user_id, branch_id="default")


@pytest.mark.asyncio
async def test_skill_permission_inherits_flow_viewer(
    di, flow_with_skill_permission, unique_id
) -> None:
    """FGA: viewer from flow → branch can_view (branch permission only adds access)."""
    user_id = f"users_{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["users"],
        company_ids=[f"skill_co_{unique_id}"],
        previous_groups=[],
    )
    channel = _a2a_channel(di, flow_with_skill_permission)
    await channel.check_permissions(user_id, branch_id="vip")


@pytest.mark.asyncio
async def test_skill_permission_granted(
    di, flow_with_skill_permission, unique_id
) -> None:
    user_id = f"vip_{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["vip"],
        company_ids=[f"skill_co_{unique_id}"],
        previous_groups=[],
    )
    channel = _a2a_channel(di, flow_with_skill_permission)
    await channel.check_permissions(user_id, branch_id="vip")


@pytest.mark.asyncio
async def test_default_skill_uses_flow_permission(
    di, flow_with_skill_permission, unique_id
) -> None:
    user_id = f"users_{unique_id}"
    await sync_user_groups(
        di.authz_service,
        user_id=user_id,
        groups=["users"],
        company_ids=[f"skill_co_{unique_id}"],
        previous_groups=[],
    )
    channel = _a2a_channel(di, flow_with_skill_permission)
    await channel.check_permissions(user_id, branch_id="default")
