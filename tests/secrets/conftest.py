"""
Secrets-специфичные фикстуры.

HTTP: secrets_client — в tests/fixtures/clients.py.
Service/repository: secrets_container, secrets_repository, secrets_service.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

API_PREFIX = "/secrets/api/v1"


@pytest.fixture
def secrets_container():
    from apps.secrets.container import get_secrets_container

    return get_secrets_container()


@pytest.fixture
def secrets_repository(secrets_container):
    return secrets_container.secrets_repository


@pytest.fixture
def secrets_service(secrets_container):
    return secrets_container.secrets_service


@pytest_asyncio.fixture
async def secrets_client_company2(secrets_app, setup_database_before_tests, auth_headers_company2):
    _ = setup_database_before_tests
    transport = ASGITransport(app=secrets_app)
    async with secrets_app.router.lifespan_context(secrets_app):
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers=auth_headers_company2,
        ) as client:
            yield client
