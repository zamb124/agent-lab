"""Разовый дебаг маркетингового сида — точечные прогоны без браузера."""

import pytest

from tests.ui.shots import seed_content

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(180)]


async def test_debug_sync_seed(
    _ui_e2e_company_resources: None,
    auth_token_system: str,
    auth_token_system_user2: str,
) -> None:
    _ = _ui_e2e_company_resources
    res = await seed_content._seed_sync(auth_token_system, auth_token_system_user2)
    print("SYNC SEED:", res)


async def test_debug_crm_seed(
    _ui_e2e_company_resources: None,
    auth_token_system: str,
) -> None:
    _ = _ui_e2e_company_resources
    res = await seed_content._seed_crm(auth_token_system)
    print("CRM SEED:", res)


async def test_debug_office_seed(
    _ui_e2e_company_resources: None,
    auth_token_system: str,
) -> None:
    _ = _ui_e2e_company_resources
    import httpx2

    origin = seed_content.api_origin("office")
    h = seed_content.bearer_headers(auth_token_system)
    async with httpx2.AsyncClient(
        base_url=origin, timeout=30.0, trust_env=False
    ) as c:
        r = await c.get("/documents/api/v1/catalogs", headers=h)
        cats = r.json().get("items", [])
        print("CATS:", [(i["title"], i["parent_catalog_id"]) for i in cats])
        ids = [str(i["catalog_id"]) for i in cats]
        r = await c.get(
            "/documents/api/v1/documents",
            params=[("catalog_ids", i) for i in ids],
            headers=h,
        )
        print("DOCS:", r.status_code, [
            (d.get("title"), d.get("file_id")) for d in r.json().get("items", [])
        ])
    res = await seed_content._seed_office(auth_token_system)
    print("OFFICE SEED:", res)
