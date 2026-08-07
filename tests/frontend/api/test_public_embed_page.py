"""Public first-party session for EmbedConfig.presentation=page."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_public_embed_page_session_requires_presentation_page(
    frontend_client: AsyncClient,
    embed_test_auth,
):
    auth_headers, flow_id, company_id, _user_id = embed_test_auth
    create = await frontend_client.post(
        "/frontend/api/embed/configs",
        headers=auth_headers,
        json={"name": "Drawer only", "flow_id": flow_id, "presentation": "drawer"},
    )
    assert create.status_code == 200
    embed_id = create.json()["embed_id"]

    origin = str(frontend_client.base_url).rstrip("/")
    denied = await frontend_client.post(
        "/frontend/api/public/embed-page/session",
        json={"embed_id": embed_id, "origin": origin},
    )
    assert denied.status_code == 403

    patch = await frontend_client.patch(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
        json={"presentation": "page"},
    )
    assert patch.status_code == 200
    assert patch.json()["presentation"] == "page"

    ok = await frontend_client.post(
        "/frontend/api/public/embed-page/session",
        json={"embed_id": embed_id, "origin": origin},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["token_type"] == "Bearer"
    assert isinstance(body["token"], str) and body["token"]
    assert body["flows_base_url"].endswith("/flows")
    assert body["flow_id"] == flow_id
    _ = company_id

    await frontend_client.delete(
        f"/frontend/api/embed/configs/{embed_id}",
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_flow_embed_page_html_served(frontend_client: AsyncClient):
    response = await frontend_client.get("/flow-embed-page?embed=embed_demo_x")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "flow-ui-page-host" in response.text
    assert "embed_demo_x" in response.text
