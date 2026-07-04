"""
Фикстуры HumanitecAgent E2E.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.agent._helpers import (
    AGENT_TEST_PUBLIC_ORIGIN,
    agent_base_url_from_token,
    pair_and_register_device,
)
from tests.agent._realtime_helpers import connect_agent_tunnel_ws


@pytest_asyncio.fixture
async def agent_base_url(
    auth_token: str,
    frontend_container,
    test_company_subdomains_initialized,
) -> str:
    _ = test_company_subdomains_initialized
    return await agent_base_url_from_token(auth_token, frontend_container)


@pytest_asyncio.fixture
async def agent_base_url_company2(
    auth_token_company2: str,
    frontend_container,
    test_company_subdomains_initialized,
) -> str:
    _ = test_company_subdomains_initialized
    return await agent_base_url_from_token(auth_token_company2, frontend_container)


@pytest_asyncio.fixture
async def agent_frontend_http_client(
    auth_token: str,
    agent_base_url: str,
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        base_url=agent_base_url,
        follow_redirects=False,
        cookies={"auth_token": auth_token},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def agent_frontend_http_anon() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        base_url=AGENT_TEST_PUBLIC_ORIGIN,
        follow_redirects=False,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def agent_frontend_http_company2(
    auth_token_company2: str,
    agent_base_url_company2: str,
) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        base_url=agent_base_url_company2,
        follow_redirects=False,
        cookies={"auth_token": auth_token_company2},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def agent_paired_device(
    agent_frontend_http_client: AsyncClient,
    auth_token: str,
    unique_id: str,
) -> tuple[str, str]:
    return await pair_and_register_device(
        agent_frontend_http_client,
        auth_cookie=auth_token,
        unique_id=unique_id,
    )


@pytest_asyncio.fixture
async def agent_tunnel_ws(agent_paired_device: tuple[str, str]) -> AsyncIterator[Any]:
    _device_id, device_token = agent_paired_device
    _ = _device_id
    async with connect_agent_tunnel_ws(device_token) as websocket:
        yield websocket


@pytest_asyncio.fixture
async def agent_tunnel_bus_pod_b(
    frontend_container,
    unique_id: str,
) -> AsyncIterator[None]:
    from apps.agent.tunnel_bus import start_tunnel_bus_listener, stop_tunnel_bus_listener

    pod_name = f"pod-b-{unique_id}"
    previous_hostname = os.environ.get("HOSTNAME")
    os.environ["HOSTNAME"] = pod_name
    await stop_tunnel_bus_listener()
    await frontend_container.redis_client.connect()
    await start_tunnel_bus_listener(frontend_container.redis_client)
    try:
        yield
    finally:
        await stop_tunnel_bus_listener()
        if previous_hostname is None:
            os.environ.pop("HOSTNAME", None)
        else:
            os.environ["HOSTNAME"] = previous_hostname
