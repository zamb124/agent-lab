"""
Channel-level тесты permissions при permissions_enabled=true.

HTTP integration с enabled=true не используется: harness через flows_permissions_enabled
(try/finally на settings, без monkeypatch). Checker matrix — test_permissions.py.
"""

from __future__ import annotations

import pytest

from apps.flows.src.channels import PermissionDenied
from core.auth.errors import PermissionDeniedA2AError


class TestChannelFlowPermission:
    """BaseChannel.check_permissions для flow-level permission."""

    @pytest.mark.asyncio
    async def test_flow_permission_denied_no_groups(
        self, container, flow_with_permission, flows_permissions_enabled
    ):
        channel = container.get_channel("a2a", flow_with_permission)
        with pytest.raises(PermissionDenied) as exc_info:
            await channel.check_permissions([], branch_id="default")
        assert isinstance(exc_info.value.error, PermissionDeniedA2AError)
        assert exc_info.value.error.code == -32008

    @pytest.mark.asyncio
    async def test_flow_permission_denied_wrong_group(
        self, container, flow_with_permission, flows_permissions_enabled
    ):
        channel = container.get_channel("a2a", flow_with_permission)
        with pytest.raises(PermissionDenied):
            await channel.check_permissions(["users", "guests"], branch_id="default")

    @pytest.mark.asyncio
    async def test_flow_permission_granted_correct_group(
        self, container, flow_with_permission, flows_permissions_enabled
    ):
        channel = container.get_channel("a2a", flow_with_permission)
        await channel.check_permissions(["managers"], branch_id="default")

    @pytest.mark.asyncio
    async def test_flow_permission_granted_admin(
        self, container, flow_with_permission, flows_permissions_enabled
    ):
        channel = container.get_channel("a2a", flow_with_permission)
        await channel.check_permissions(["admin"], branch_id="default")


class TestChannelSkillPermission:
    """BaseChannel.check_permissions для branch-level permission."""

    @pytest.mark.asyncio
    async def test_skill_permission_denied(
        self, container, flow_with_skill_permission, flows_permissions_enabled
    ):
        channel = container.get_channel("a2a", flow_with_skill_permission)
        with pytest.raises(PermissionDenied) as exc_info:
            await channel.check_permissions(["users"], branch_id="vip")
        message = exc_info.value.error.message.lower()
        assert "branch" in message or "vip" in message

    @pytest.mark.asyncio
    async def test_skill_permission_granted(
        self, container, flow_with_skill_permission, flows_permissions_enabled
    ):
        channel = container.get_channel("a2a", flow_with_skill_permission)
        await channel.check_permissions(["vip"], branch_id="vip")

    @pytest.mark.asyncio
    async def test_default_skill_uses_flow_permission(
        self, container, flow_with_skill_permission, flows_permissions_enabled
    ):
        channel = container.get_channel("a2a", flow_with_skill_permission)
        await channel.check_permissions(["users"], branch_id="default")
