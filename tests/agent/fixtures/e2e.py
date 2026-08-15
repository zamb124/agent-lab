"""
Фикстуры HumanitecAgent E2E (HTTP/tunnel).

Загружаются через pytest_plugins в tests/conftest.py, не через tests/agent/conftest.py:
иначе при совместном сборе tests/agent/* и tests/ui/* pytest регистрирует модуль дважды.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx import AsyncClient, Timeout

from tests.agent._helpers import (
    AGENT_TEST_PUBLIC_ORIGIN,
    agent_base_url_from_token,
    loopback_frontend_http_target,
    pair_and_register_device,
)
from tests.agent._realtime_helpers import connect_agent_tunnel_ws

# Pairing/register к company Host под нагрузкой Electron; default httpx 5s → ConnectTimeout.
_AGENT_HTTP_TIMEOUT = Timeout(30.0, connect=10.0)


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
    base_url, host_headers = loopback_frontend_http_target(agent_base_url)
    async with AsyncClient(
        base_url=base_url,
        headers=host_headers,
        follow_redirects=False,
        cookies={"auth_token": auth_token},
        timeout=_AGENT_HTTP_TIMEOUT,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def agent_frontend_http_client_system(
    auth_token_system: str,
    frontend_container,
    test_company_subdomains_initialized,
) -> AsyncIterator[AsyncClient]:
    _ = test_company_subdomains_initialized
    public_origin = await agent_base_url_from_token(auth_token_system, frontend_container)
    base_url, host_headers = loopback_frontend_http_target(public_origin)
    async with AsyncClient(
        base_url=base_url,
        headers=host_headers,
        follow_redirects=False,
        cookies={"auth_token": auth_token_system},
        timeout=_AGENT_HTTP_TIMEOUT,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def agent_frontend_http_anon() -> AsyncIterator[AsyncClient]:
    base_url, host_headers = loopback_frontend_http_target(AGENT_TEST_PUBLIC_ORIGIN)
    async with AsyncClient(
        base_url=base_url,
        headers=host_headers,
        follow_redirects=False,
        timeout=_AGENT_HTTP_TIMEOUT,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def agent_frontend_http_company2(
    auth_token_company2: str,
    agent_base_url_company2: str,
) -> AsyncIterator[AsyncClient]:
    base_url, host_headers = loopback_frontend_http_target(agent_base_url_company2)
    async with AsyncClient(
        base_url=base_url,
        headers=host_headers,
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
