"""Integration tests: internal company init and MCP init error propagation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx2 import ASGITransport, AsyncClient

from apps.flows.src.tasks.company_init_tasks import init_company_resources
from core.internal_context_headers import build_internal_context_headers
from core.utils.tokens import get_token_service


@pytest.mark.asyncio
async def test_internal_company_init_accepts_signed_headers(
    app,
    auth_token_company2: str,
) -> None:
    """Trusted peer может запланировать init через /internal/company/init."""
    token_data = get_token_service().validate_token(auth_token_company2)
    headers = build_internal_context_headers(
        company_id="company2",
        user_id=token_data.user_id,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            "/flows/api/v1/internal/company/init",
            json={
                "company_id": "company2",
                "company_name": "Company Two",
                "subdomain": "company2",
            },
            headers=headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["task_id"], str)
    assert body["task_id"]
    assert body["status"] == "scheduled"


@pytest.mark.asyncio
async def test_init_company_resources_reraises_mcp_errors(di) -> None:
    """MCP ошибки при init не проглатываются — TaskIQ может retry."""
    with patch(
        "apps.flows.src.tasks.company_init_tasks.ensure_default_mcp_servers_for_company",
        new_callable=AsyncMock,
    ) as ensure_default:
        ensure_default.side_effect = RuntimeError("mcp init failed")
        with pytest.raises(RuntimeError, match="mcp init failed"):
            _ = await init_company_resources(
                company_id="mcp_error_company",
                company_name="MCP Error Co",
                subdomain="mcperror",
                di=di,
            )
