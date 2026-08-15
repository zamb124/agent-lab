"""IntegrationExternalAuthorService: pre-provision и ключ маппинга в shared storage."""


from __future__ import annotations

from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401
import json
from typing import cast

import pytest

from apps.crm.container import CRMContainer
from core.identity.integration_external_author import (
    IntegrationExternalAuthorService,
    integration_external_author_storage_key,
)
from core.models.identity_models import Company, User
from tests.crm.e2e._json_helpers import json_object

pytestmark = pytest.mark.timeout(30, func_only=True)


@pytest.mark.asyncio
async def test_resolve_creates_user_and_mapping(
    crm_container: CRMContainer,
    unique_id: str,
) -> None:
    company_id = f"ext_author_co_{unique_id}"
    company = Company(
        company_id=company_id,
        name=f"External Author Test {unique_id}",
        members={},
    )
    _ = await crm_container.company_repository.set(company)
    provider = "amocrm"
    account = f"sub_{unique_id}"
    ext = "999001"
    email = f"extauthor_{unique_id}@test.local"

    svc = IntegrationExternalAuthorService(
        storage=crm_container.shared_storage,
        user_repository=crm_container.user_repository,
        company_repository=crm_container.company_repository,
        authz=crm_container.authz_service,
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
