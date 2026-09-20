"""Health живого стека: Centrifugo v6 + bus Granian — те же hop'ы, что в проде."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_centrifugo_health(centrifugo_http: AsyncClient) -> None:
    response = await centrifugo_http.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_realtime_bus_health(realtime_client_http: AsyncClient) -> None:
    response = await realtime_client_http.get("/health")
    assert response.status_code == 200
