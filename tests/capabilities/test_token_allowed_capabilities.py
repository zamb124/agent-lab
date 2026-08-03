"""Enforcement allowed_capabilities в capability execution token."""

from __future__ import annotations

import pytest

from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.capabilities.tokens import assert_capability_allowed


def _signed_context(*, allowed_capabilities: list[str]) -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id="token_test_user",
        flow_id="token_test_flow",
        branch_id="main",
        session_id="token_test_flow:ctx",
        task_id="token_task",
        context_id="ctx",
        channel="a2a",
        allowed_capabilities=allowed_capabilities,
        exp=execution_token_exp(300),
    )
    token = issue_execution_token(claims)
    return CapabilityExecutionContext(
        execution_token=token,
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
    )


def test_assert_capability_allowed_empty_list_permits_all() -> None:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        flow_id="f",
        branch_id="main",
        session_id="f:c",
        task_id="t",
        context_id="c",
        channel="a2a",
        allowed_capabilities=[],
        exp=execution_token_exp(300),
    )
    assert_capability_allowed(claims, "files.create")


def test_assert_capability_allowed_denies_missing_capability() -> None:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        flow_id="f",
        branch_id="main",
        session_id="f:c",
        task_id="t",
        context_id="c",
        channel="a2a",
        allowed_capabilities=["files.create"],
        exp=execution_token_exp(300),
    )
    with pytest.raises(ValueError, match="Capability not allowed"):
        assert_capability_allowed(claims, "http.get")


@pytest.mark.asyncio
async def test_registry_call_denies_capability_not_in_token() -> None:
    from apps.capability_gateway.container import get_capability_gateway_container

    container = get_capability_gateway_container()
    context = _signed_context(allowed_capabilities=["files.create"])
    request = CapabilityCallRequest(
        context=context,
        name="http.get",
        kwargs={"url": "https://example.com"},
    )
    with pytest.raises(ValueError, match="Capability not allowed"):
        await container.capability_registry.call(request)
