"""FGA membership + company context for flow tool unit tests (real AuthzService gate)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio

from tests.flows._tool_authz_context import bind_flow_tool_authz_context


@pytest_asyncio.fixture(autouse=True)
async def _tool_tests_authz_context() -> AsyncIterator[None]:
    async for _ in bind_flow_tool_authz_context():
        yield
