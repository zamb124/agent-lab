from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.frontend.documentation_mount import mount_documentation_static


@pytest.mark.asyncio
async def test_documentation_mount_serves_dist_created_after_app_start(tmp_path):
    app = FastAPI()
    mount_documentation_static(app, tmp_path)

    dist = tmp_path / "documentation-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>Docs</h1>", encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        redirect_response = await client.get("/documentation", follow_redirects=False)
        response = await client.get("/documentation/")

    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == "/documentation/"
    assert response.status_code == 200
    assert "<h1>Docs</h1>" in response.text


@pytest.mark.asyncio
async def test_documentation_mount_serves_gateway_prefix_created_after_app_start(tmp_path):
    app = FastAPI()
    mount_documentation_static(app, tmp_path, gateway_prefix="frontend")

    dist = tmp_path / "documentation-dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>Frontend docs</h1>", encoding="utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        redirect_response = await client.get("/frontend/documentation", follow_redirects=False)
        response = await client.get("/frontend/documentation/")

    assert redirect_response.status_code == 307
    assert redirect_response.headers["location"] == "/frontend/documentation/"
    assert response.status_code == 200
    assert "<h1>Frontend docs</h1>" in response.text
