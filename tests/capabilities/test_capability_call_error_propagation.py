"""4xx от peer (tool-runtime) через capability-gateway не маскируются под 500."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.capability_gateway.api.v1.capabilities import call_capability
from core.capabilities import CapabilityCallRequest, CapabilityExecutionContext
from core.clients.service_client import ServiceClientError


def _call_request() -> CapabilityCallRequest:
    return CapabilityCallRequest(
        context=CapabilityExecutionContext(
            execution_token="test-token",
            company_id="system",
            user_id="user-1",
            flow_id="flow-1",
            branch_id="main",
            session_id="flow-1:ctx-1",
            task_id="task-1",
            context_id="ctx-1",
            channel="editor",
        ),
        name="tools.ask_user",
        kwargs={},
    )


@pytest.mark.asyncio
async def test_call_capability_propagates_peer_422_detail() -> None:
    di = MagicMock()
    di.capability_registry.call = AsyncMock(
        side_effect=ServiceClientError(
            'HTTP 422 при запросе к flows: {"detail":{"tool_id":"ask_user"}}',
            status_code=422,
            response_text='{"detail":{"tool_id":"ask_user","message":"Tool arguments failed validation"}}',
        )
    )

    with pytest.raises(HTTPException) as raised:
        await call_capability(di, _call_request())

    assert raised.value.status_code == 422
    detail = raised.value.detail
    assert isinstance(detail, dict)
    assert detail["tool_id"] == "ask_user"
    assert detail["message"] == "Tool arguments failed validation"


@pytest.mark.asyncio
async def test_call_capability_keeps_peer_500_as_exception() -> None:
    di = MagicMock()
    di.capability_registry.call = AsyncMock(
        side_effect=ServiceClientError(
            "HTTP 500 при запросе к flows: boom",
            status_code=500,
            response_text='{"detail":"boom"}',
        )
    )

    with pytest.raises(ServiceClientError) as raised:
        await call_capability(di, _call_request())

    assert raised.value.status_code == 500
