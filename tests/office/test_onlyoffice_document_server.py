"""
Живой OnlyOffice Document Server: healthcheck по публичному URL (docker-compose-test / dev).
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.timeout(60)]


@pytest.mark.asyncio
async def test_onlyoffice_document_server_healthcheck():
    base = os.environ.get("OFFICE__DOCUMENT_SERVER_PUBLIC_URL", "").strip().rstrip("/")
    if not base:
        pytest.fail("OFFICE__DOCUMENT_SERVER_PUBLIC_URL не задан")
    url = f"{base}/healthcheck"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url)
    except httpx.ConnectError as exc:
        pytest.fail(f"Document Server недоступен: {url}: {exc}")
    assert response.status_code == 200
