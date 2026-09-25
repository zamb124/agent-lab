"""
Интеграционные тесты доступности companies API во всех сервисах.
"""


from __future__ import annotations

import pytest

from core.api.companies import CompanyMembershipResponse, build_my_companies_response
from core.models.identity_models import Company, User
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.timeout(120)
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


@pytest.mark.asyncio
async def test_build_my_companies_response_returns_items_list_response(
    app, unique_id: str
) -> None:
    _ = app
    company_id = f"co-{unique_id}"
    user_id = f"user-{unique_id}"
    subdomain = f"co-{unique_id}"
    user = User(
        user_id=user_id,
        name="Test User",
        emails=[f"{user_id}@example.com"],
        companies={company_id: ["owner"]},
        active_company_id=company_id,
    )
    company = Company(
        company_id=company_id,
        name="Company One",
        subdomain=subdomain,
        owner_user_id=user_id,
        members={user_id: ["owner"]},
    )
    _ = await User.set(user)
    _ = await Company.set(company)
    try:
        response = await build_my_companies_response(user=user)
        assert isinstance(response.items, list)
        assert response.items == [
            CompanyMembershipResponse(
                company_id=company_id,
                name="Company One",
                subdomain=subdomain,
                role=["owner"],
                is_active=True,
            )
        ]
    finally:
        _ = await Company.delete_by_id(company_id)
        _ = await User.delete_by_id(user_id)
