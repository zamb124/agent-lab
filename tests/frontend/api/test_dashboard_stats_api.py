"""REST-зеркало `frontend/dashboard/stats_requested`: счётчики витрины от владельцев."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

pytestmark = pytest.mark.timeout(60, func_only=True)


@pytest.mark.asyncio
async def test_dashboard_stats_for_system_company(frontend_client: AsyncClient, auth_headers_system) -> None:
    response = await frontend_client.get("/frontend/api/dashboard/stats", headers=auth_headers_system)
    assert response.status_code == 200, response.text
    stats = response.json()
    for field in ("flows_total", "namespaces_total", "rag_namespaces_total", "documents_files_total"):
        assert isinstance(stats[field], int) and stats[field] >= 0, field
    assert isinstance(stats["litserve_models_total"], int)


@pytest.mark.asyncio
async def test_dashboard_stats_hides_litserve_outside_system(frontend_client: AsyncClient, auth_headers) -> None:
    response = await frontend_client.get("/frontend/api/dashboard/stats", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["litserve_models_total"] is None


@pytest.mark.asyncio
async def test_dashboard_stats_requires_session(frontend_client: AsyncClient) -> None:
    response = await frontend_client.get("/frontend/api/dashboard/stats")
    assert response.status_code in (401, 403)
