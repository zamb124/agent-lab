"""REST-зеркало `search/providers/*`: BYOK-ключи и порядок провайдеров компании."""

from __future__ import annotations

import pytest
from httpx2 import ASGITransport, AsyncClient

from core.ai.company_settings import decrypt_secret
from core.company_search import COMPANY_SEARCH_METADATA_KEY, CompanySearchProviders
from core.models.identity_models import Company
from core.utils.tokens import get_token_service
from tests.fixtures.clients import _PLATFORM_ASGI_BASE_URL, _PLATFORM_ASGI_HOST_HEADERS

pytestmark = pytest.mark.timeout(60, func_only=True)

PROVIDERS_URL = "/search/api/v1/providers/company"


@pytest.fixture
async def search_company_client(search_app, setup_database_before_tests, auth_headers):
    """Клиент Search API от имени админа обычной компании (не system)."""
    _ = setup_database_before_tests
    async with search_app.router.lifespan_context(search_app):
        async with AsyncClient(
            transport=ASGITransport(app=search_app),
            base_url=_PLATFORM_ASGI_BASE_URL,
            headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers},
        ) as client:
            yield client


def _company_id(auth_headers: dict[str, str]) -> str:
    token_data = get_token_service().validate_token(auth_headers["Authorization"].replace("Bearer ", ""))
    assert token_data is not None
    return token_data.company_id


@pytest.mark.asyncio
async def test_search_providers_company_key_crud(search_company_client, search_di, auth_headers):
    """Search provider BYOK сохраняется за компанией, шифруется и отдаётся в UI только маской."""
    company_id = _company_id(auth_headers)

    snapshot = await search_company_client.get(PROVIDERS_URL)
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["provider_order"] == ["tinyfish", "linkup", "serper", "tavily"]
    assert [item["provider_id"] for item in body["providers"]] == ["tinyfish", "linkup", "serper", "tavily"]

    response = await search_company_client.put(
        f"{PROVIDERS_URL}/tavily",
        json={
            "enabled": True,
            "credential_source": "company",
            "api_key": "tvly-company-secret",
            "base_url": "https://api.tavily.com",
            "timeout_seconds": 14,
            "search_depth": "advanced",
            "topic": "news",
            "include_answer": True,
        },
    )
    assert response.status_code == 200

    company = await Company.get(company_id)
    assert company is not None
    settings = CompanySearchProviders.from_metadata(company.metadata)
    assert settings.tavily.credential_source == "company"
    assert settings.tavily.api_key_encrypted is not None
    assert decrypt_secret(settings.tavily.api_key_encrypted) == "tvly-company-secret"
    assert settings.tavily.search_depth == "advanced"
    assert settings.tavily.topic == "news"
    assert settings.tavily.include_answer is True

    changed = await search_company_client.get(PROVIDERS_URL)
    assert changed.status_code == 200
    tavily = next(item for item in changed.json()["providers"] if item["provider_id"] == "tavily")
    assert tavily["credential_source"] == "company"
    assert tavily["configured"] is True
    assert tavily["key_masked"] == "**** cret"

    reset = await search_company_client.delete(f"{PROVIDERS_URL}/tavily")
    assert reset.status_code == 200
    company = await Company.get(company_id)
    assert company is not None
    assert COMPANY_SEARCH_METADATA_KEY not in company.metadata


@pytest.mark.asyncio
async def test_search_provider_order_is_company_scoped(search_company_client, search_di, auth_headers):
    """Порядок Search providers хранится в metadata активной компании."""
    company_id = _company_id(auth_headers)

    response = await search_company_client.put(
        f"{PROVIDERS_URL}/order",
        json={"provider_order": ["tavily", "serper"]},
    )
    assert response.status_code == 200

    company = await Company.get(company_id)
    assert company is not None
    settings = CompanySearchProviders.from_metadata(company.metadata)
    assert settings.provider_order == ["tavily", "serper", "tinyfish", "linkup"]

    snapshot = await search_company_client.get(PROVIDERS_URL)
    assert snapshot.status_code == 200
    assert snapshot.json()["provider_order"] == ["tavily", "serper", "tinyfish", "linkup"]
