"""IntegrationExternalAuthorService: pre-provision и ключ маппинга в shared storage."""

from __future__ import annotations

import json
from typing import cast

import pytest

from apps.crm.container import CRMContainer
from core.identity.integration_external_author import (
    IntegrationExternalAuthorService,
    integration_external_author_storage_key,
)
from core.identity.system_bootstrap import ensure_system_company_exists
from core.models.identity_models import User
from tests.crm.e2e._json_helpers import json_object

pytestmark = pytest.mark.timeout(30, func_only=True)


@pytest.mark.asyncio
async def test_resolve_creates_user_and_mapping(
    crm_container: CRMContainer,
    unique_id: str,
) -> None:
    _ = await ensure_system_company_exists(
        company_repository=crm_container.company_repository,
        subdomain_repository=crm_container.subdomain_repository,
    )
    company_id = "system"
    provider = "amocrm"
    account = f"sub_{unique_id}"
    ext = "999001"
    email = f"extauthor_{unique_id}@test.local"

    svc = IntegrationExternalAuthorService(
        storage=crm_container.shared_storage,
        user_repository=crm_container.user_repository,
        company_repository=crm_container.company_repository,
    )
    uid1 = await svc.resolve_platform_user_id(
        company_id=company_id,
        provider_id=provider,
        account_key=account,
        external_user_id=ext,
        email=email,
        display_name="Amo User",
    )
    uid2 = await svc.resolve_platform_user_id(
        company_id=company_id,
        provider_id=provider,
        account_key=account,
        external_user_id=ext,
        email=email,
        display_name="Amo User",
    )
    assert uid1 == uid2
    user = await crm_container.user_repository.get(uid1)
    assert user is not None
    assert email in user.emails
    assert company_id in user.companies
    company = await crm_container.company_repository.get(company_id)
    assert company is not None
    assert uid1 in company.members

    key = integration_external_author_storage_key(company_id, provider, account, ext)
    raw = await crm_container.shared_storage.get(key, force_global=True)
    assert raw is not None
    mapping = json_object(cast(object, json.loads(raw)))
    assert mapping["user_id"] == uid1


@pytest.mark.asyncio
async def test_find_all_by_email_ci_finds_mixed_case(
    crm_container: CRMContainer,
    unique_id: str,
) -> None:
    email_lower = f"mixed_{unique_id}@test.local"
    user = User(
        user_id=f"user_mixed_{unique_id}",
        name="Mixed",
        emails=[f"Mixed_{unique_id}@TEST.LOCAL"],
        companies={},
        active_company_id="",
    )
    _ = await crm_container.user_repository.set(user)
    found = await crm_container.user_repository.find_all_by_email_ci(email_lower)
    assert any(candidate.user_id == user.user_id for candidate in found)
