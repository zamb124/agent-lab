"""4xx tool-runtime через capability-gateway остаётся ошибкой команды, 5xx — ошибкой peer."""

from __future__ import annotations

import pytest

from apps.capability_gateway.api.v1.capabilities import call_capability
from apps.capability_gateway.di import CapabilityGatewayDi
from apps.flows.di import FlowsDi
from core.capabilities import (
    CapabilityCallRequest,
    CapabilityExecutionContext,
    CapabilityExecutionTokenClaims,
    execution_token_exp,
    issue_execution_token,
)
from core.clients.service_client import ServiceClientError
from core.websocket import WsCommandError


def _signed_context(
    *,
    user_id: str,
    allowed_capabilities: list[str],
) -> CapabilityExecutionContext:
    claims = CapabilityExecutionTokenClaims(
        company_id="system",
        user_id=user_id,
        flow_id="capability_error_flow",
        branch_id="main",
        session_id="capability_error_flow:ctx",
        task_id="capability-error-task",
        context_id="ctx",
        channel="a2a",
        allowed_capabilities=allowed_capabilities,
        exp=execution_token_exp(300),
    )
    return CapabilityExecutionContext(
        execution_token=issue_execution_token(claims),
        company_id=claims.company_id,
        user_id=claims.user_id,
        flow_id=claims.flow_id,
        branch_id=claims.branch_id,
        session_id=claims.session_id,
        task_id=claims.task_id,
        context_id=claims.context_id,
        channel=claims.channel,
    )


def _request(
    context: CapabilityExecutionContext,
    *,
    name: str,
    kwargs: dict[str, str],
) -> CapabilityCallRequest:
    return CapabilityCallRequest(
        context=context,
        name=name,
        kwargs=kwargs,
        state={
            "task_id": context.task_id,
            "context_id": context.context_id,
            "user_id": context.user_id,
            "session_id": context.session_id,
        },
    )


@pytest.mark.asyncio
async def test_call_capability_propagates_invalid_tool_arguments(
    capability_gateway_di: CapabilityGatewayDi,
    di: FlowsDi,
) -> None:
    _ = di
    context = _signed_context(user_id="test_user", allowed_capabilities=["tools.ask_user"])
    with pytest.raises(WsCommandError) as raised:
        await call_capability(
            capability_gateway_di,
            _request(context, name="tools.ask_user", kwargs={}),
        )

    assert raised.value.code == "ws_invalid_payload"
    assert "ask_user" in raised.value.detail
    assert "arguments failed validation" in raised.value.detail


@pytest.mark.asyncio
async def test_call_capability_keeps_peer_500_as_exception(
    capability_gateway_di: CapabilityGatewayDi,
    di: FlowsDi,
) -> None:
    _ = di
    context = _signed_context(
        user_id="test_user",
        allowed_capabilities=["tools.hitl_operator_task"],
    )
    with pytest.raises(ServiceClientError) as raised:
        await call_capability(
            capability_gateway_di,
            _request(
                context,
                name="tools.hitl_operator_task",
                kwargs={
                    "question": "Need a decision",
                    "task_title": "Decision",
                    "assignee_queue": "ops",
                },
            ),
        )

    assert raised.value.status_code == 500
