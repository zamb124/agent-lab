"""
Интеграционные тесты доступности companies API во всех сервисах.
"""

from __future__ import annotations

import pytest
from core.api.companies import build_my_companies_response
from core.models.identity_models import Company, User


@pytest.mark.asyncio
async def test_frontend_companies_me_endpoint_returns_list_response(
    unique_id: str,
    frontend_client,
    auth_headers,
) -> None:
    _ = unique_id
    response = await frontend_client.get("/frontend/api/companies/me", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert "items" in payload
    assert isinstance(payload["items"], list)


class _CompanyRepositoryStub:
    def __init__(self, company: Company) -> None:
        self._company = company

    async def get(self, company_id: str) -> Company | None:
        if company_id != self._company.company_id:
            return None
        return self._company


@pytest.mark.asyncio
async def test_build_my_companies_response_returns_items_list_response() -> None:
    user = User(
        user_id="user-1",
        name="Test User",
        email="user-1@example.com",
        companies={"company-1": ["owner"]},
        active_company_id="company-1",
    )
    company = Company(
        company_id="company-1",
        name="Company One",
        subdomain="company-one",
        owner_user_id="user-1",
        members={"user-1": ["owner"]},
    )
    response = await build_my_companies_response(
        user=user,
        company_repository=_CompanyRepositoryStub(company),
    )
    assert isinstance(response.items, list)
    assert response.items == [
        {
            "company_id": "company-1",
            "name": "Company One",
            "subdomain": "company-one",
            "role": ["owner"],
            "is_active": True,
        }
    ]
