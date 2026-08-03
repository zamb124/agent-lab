"""CapabilityGatewayClient against ASGI capability-gateway."""

from __future__ import annotations

import pytest

from core.clients.capability_gateway_client import CapabilityGatewayClient

pytestmark = pytest.mark.asyncio


async def test_capability_gateway_client_get_documentation() -> None:
    docs = await CapabilityGatewayClient().get_documentation("python")
    assert docs.markdown.strip()
    assert docs.version.strip()
    assert docs.language == "python"
    assert docs.namespaces
