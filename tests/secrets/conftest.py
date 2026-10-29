"""
Secrets-специфичные фикстуры.

HTTP: secrets_client — в tests/fixtures/clients.py.
DI: secrets_di — тот же ``SecretsDi``, что собирает lifespan приложения.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient

from apps.secrets.di import SecretsDi
from core.di import require_di

API_PREFIX = "/secrets/api/v1"


@pytest_asyncio.fixture
async def secrets_di(secrets_app: FastAPI, setup_database_before_tests: None) -> AsyncIterator[SecretsDi]:
    _ = setup_database_before_tests
    async with secrets_app.router.lifespan_context(secrets_app):
        yield require_di(secrets_app, SecretsDi)


@pytest_asyncio.fixture
async def secrets_client_company2(
    secrets_app: FastAPI,
    setup_database_before_tests: None,
    auth_headers_company2: dict[str, str],
) -> AsyncIterator[AsyncClient]:
    _ = setup_database_before_tests
    transport = ASGITransport(app=secrets_app)
    async with secrets_app.router.lifespan_context(secrets_app):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=auth_headers_company2,
        ) as client:
            yield client
