"""E2E: Sync/CRM namespace list excludes personal and technical kinds."""

from __future__ import annotations

import pytest

from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from core.models.i18n_models import Language
from core.models.identity_models import Company, NamespaceKind, User
from core.namespace import personal_namespace_name
from tests.sync.api._helpers import seed_namespace_via_repo


@pytest.mark.asyncio
async def test_sync_list_namespaces_excludes_personal_and_technical(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
    sync_di,
) -> None:
    company = await Company.get(company_id)
    assert company is not None
    owner_id = company.owner_user_id
    owner = await User.get(owner_id)
    assert owner is not None

    workspace = f"ws_sync_{unique_id}"
    await seed_namespace_via_repo(sync_di, company_id, workspace)

    previous = get_context()
    set_context(
        Context(
            user=owner,
            active_company=company,
            user_companies=[company],
            channel="test",
            language=Language.RU,
        )
    )
    try:
        sync_ns = sync_di.namespace_service
        _ = await sync_ns.ensure_personal_namespace(
            owner_id, display_name=owner.name
        )
        tech = f"office-catalog-sync-{unique_id}"
        _ = await sync_ns.get_or_create(
            tech,
            description="tech",
            kind=NamespaceKind.TECHNICAL,
        )
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)

    r = await sync_client.get("/sync/api/v1/namespaces", headers=sync_auth_headers)
    assert r.status_code == 200, r.text
    names = {item["name"] for item in r.json()["items"]}
    assert workspace in names
    assert personal_namespace_name(owner_id) not in names
    assert tech not in names
