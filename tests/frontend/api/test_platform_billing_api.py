"""
API platform-billing: доступ system, цены, отчёт usage.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.billing.service import company_resource_prices_storage_key, company_settlement_rules_storage_key
from core.models.identity_models import Company


@pytest_asyncio.fixture
async def frontend_client_system(frontend_app, auth_token_system):
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://testserver",
        cookies={"auth_token": auth_token_system},
        follow_redirects=True,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_platform_billing_prices_forbidden_non_system(frontend_client_with_auth):
    response = await frontend_client_with_auth.get("/frontend/api/platform-billing/prices")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_platform_billing_prices_system(frontend_client_system):
    response = await frontend_client_system.get("/frontend/api/platform-billing/prices")
    assert response.status_code == 200
    data = response.json()
    assert "effective" in data
    assert isinstance(data["effective"], dict)


@pytest.mark.asyncio
async def test_platform_billing_put_prices_roundtrip(frontend_client_system, frontend_container):
    key = "billing:resource_base_prices_json"
    await frontend_container.shared_storage.delete(key, force_global=True)

    payload = {"llm": {"*": 0.042}}
    response = await frontend_client_system.put(
        "/frontend/api/platform-billing/prices",
        json=payload,
    )
    assert response.status_code == 200

    raw = await frontend_container.shared_storage.get(key, force_global=True)
    assert raw is not None
    assert json.loads(raw) == payload

    get_response = await frontend_client_system.get("/frontend/api/platform-billing/prices")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["storage_override"] == payload
    assert body["effective"]["llm"]["*"] == 0.042

    await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_platform_billing_usage_report_system(frontend_client_system):
    response = await frontend_client_system.get(
        "/frontend/api/platform-billing/usage-report",
        params={"limit": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_platform_billing_facets_usage_types_forbidden_non_system(frontend_client_with_auth):
    response = await frontend_client_with_auth.get("/frontend/api/platform-billing/facets/usage-types")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_platform_billing_facets_usage_types_system(frontend_client_system):
    response = await frontend_client_system.get("/frontend/api/platform-billing/facets/usage-types")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    values = {item["value"] for item in data["items"]}
    assert "tool_call" in values
    assert "llm_request" in values


@pytest.mark.asyncio
async def test_platform_billing_facets_resource_names_system(frontend_client_system):
    response = await frontend_client_system.get("/frontend/api/platform-billing/facets/resource-names")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_platform_billing_settlement_rules_roundtrip(frontend_client_system, frontend_container, unique_id):
    cid = "system"
    key = company_settlement_rules_storage_key(cid)
    prev = await frontend_container.shared_storage.get(key, force_global=True)
    try:
        body = {
            "version": 1,
            "application_mode": "all_matching",
            "rules": [
                {
                    "rule_id": f"api_rule_{unique_id}",
                    "enabled": True,
                    "priority": 10,
                    "resource_name": "llm:*",
                    "usage_type": "llm_request",
                    "quantity_from": "const:1",
                    "match": {"operation_name_prefix": "x."},
                }
            ],
        }
        put_r = await frontend_client_system.put(
            f"/frontend/api/platform-billing/settlement-rules/{cid}",
            json=body,
        )
        assert put_r.status_code == 200
        get_r = await frontend_client_system.get(f"/frontend/api/platform-billing/settlement-rules/{cid}")
        assert get_r.status_code == 200
        doc = get_r.json()["document"]
        assert doc["rules"][0]["rule_id"] == f"api_rule_{unique_id}"
    finally:
        if prev is not None:
            await frontend_container.shared_storage.set(key, prev, force_global=True)
        else:
            await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_platform_billing_settlement_rules_invalid_422(frontend_client_system):
    body = {
        "version": 1,
        "application_mode": "all_matching",
        "rules": [
            {
                "rule_id": "bad_usage",
                "resource_name": "llm:*",
                "usage_type": "not_a_real_usage_type",
                "match": {},
            }
        ],
    }
    response = await frontend_client_system.put(
        "/frontend/api/platform-billing/settlement-rules/system",
        json=body,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_billing_settlement_rules_unknown_company_404(frontend_client_system, unique_id):
    cid = f"no_such_company_{unique_id}"
    response = await frontend_client_system.get(f"/frontend/api/platform-billing/settlement-rules/{cid}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_platform_billing_company_prices_roundtrip(frontend_client_system, frontend_container, unique_id):
    cid = f"co_price_{unique_id}"
    key = company_resource_prices_storage_key(cid)
    await frontend_container.shared_storage.delete(key, force_global=True)
    payload = {"llm": {"*": 77.1}}
    put_r = await frontend_client_system.put(
        f"/frontend/api/platform-billing/prices/company/{cid}",
        json=payload,
    )
    assert put_r.status_code == 200
    get_r = await frontend_client_system.get(f"/frontend/api/platform-billing/prices/company/{cid}")
    assert get_r.status_code == 200
    data = get_r.json()
    assert data["company_id"] == cid
    assert data["storage_override"] == payload
    await frontend_container.shared_storage.delete(key, force_global=True)


@pytest.mark.asyncio
async def test_platform_billing_put_prices_invalid_catalog_422(frontend_client_system):
    response = await frontend_client_system.put(
        "/frontend/api/platform-billing/prices",
        json={"llm": "not-a-dict"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_billing_put_prices_tool_category_rejected_422(frontend_client_system):
    response = await frontend_client_system.put(
        "/frontend/api/platform-billing/prices",
        json={"tool": {"*": 1.0}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_billing_put_settlement_rules_tool_resource_rejected_422(
    frontend_client_system,
):
    body = {
        "version": 1,
        "application_mode": "all_matching",
        "rules": [
            {
                "rule_id": "bad_tool_res",
                "enabled": True,
                "priority": 1,
                "resource_name": "tool:external_api",
                "usage_type": "tool_call",
                "quantity_from": "const:1",
                "match": {"operation_name_prefix": "x."},
            }
        ],
    }
    response = await frontend_client_system.put(
        "/frontend/api/platform-billing/settlement-rules/system",
        json=body,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_billing_put_company_prices_invalid_422(
    frontend_client_system, unique_id: str,
):
    cid = f"co_bad_{unique_id}"
    response = await frontend_client_system.put(
        f"/frontend/api/platform-billing/prices/company/{cid}",
        json={"x": 1},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_billing_put_company_prices_tool_category_rejected_422(
    frontend_client_system, unique_id: str,
):
    cid = f"co_tool_{unique_id}"
    response = await frontend_client_system.put(
        f"/frontend/api/platform-billing/prices/company/{cid}",
        json={"tool": {"*": 1.0}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_billing_get_company_prices_whitespace_id_422(frontend_client_system):
    response = await frontend_client_system.get("/frontend/api/platform-billing/prices/company/%20")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_billing_company_resolve_by_company_id(frontend_client_system):
    response = await frontend_client_system.get(
        "/frontend/api/platform-billing/company-resolve",
        params={"q": "system"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["company_id"] == "system"
    assert data["name"]


@pytest.mark.asyncio
async def test_platform_billing_company_resolve_by_subdomain_slug(
    frontend_client_system,
    frontend_container,
    unique_id: str,
    system_user_id: str,
) -> None:
    slug = f"bl-{unique_id}"
    cid = f"co_slug_{unique_id}"
    company = Company(
        company_id=cid,
        name=f"Billing slug test {unique_id}",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        subdomain=slug,
    )
    await frontend_container.company_repository.set(company)
    await frontend_container.subdomain_repository.set_mapping(slug, cid)
    try:
        by_slug = await frontend_client_system.get(
            "/frontend/api/platform-billing/company-resolve",
            params={"q": slug},
        )
        assert by_slug.status_code == 200
        assert by_slug.json()["company_id"] == cid

        mixed = await frontend_client_system.get(
            "/frontend/api/platform-billing/company-resolve",
            params={"q": slug.upper()},
        )
        assert mixed.status_code == 200
        assert mixed.json()["company_id"] == cid
    finally:
        await frontend_container.subdomain_repository.delete(slug)
        await frontend_container.company_repository.delete(cid)


@pytest.mark.asyncio
async def test_platform_billing_company_resolve_unknown_404(frontend_client_system, unique_id: str):
    response = await frontend_client_system.get(
        "/frontend/api/platform-billing/company-resolve",
        params={"q": f"zzz_no_company_{unique_id}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_platform_billing_facets_billing_companies(frontend_client_system):
    response = await frontend_client_system.get(
        "/frontend/api/platform-billing/facets/billing-companies",
        params={"limit": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_platform_billing_default_settlement_rules_template(frontend_client_system):
    response = await frontend_client_system.get("/frontend/api/platform-billing/default-settlement-rules")
    assert response.status_code == 200
    data = response.json()
    doc = data["document"]
    assert doc.get("application_mode") == "first_win"
    assert isinstance(doc.get("rules"), list)
    assert len(doc["rules"]) >= 5
