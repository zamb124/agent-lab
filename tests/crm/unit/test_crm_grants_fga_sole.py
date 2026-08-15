"""CRM grants / public projection — только OpenFGA."""


from __future__ import annotations

import pytest

from apps.crm.db.models import CRMEntity
from apps.crm.services.access_grant_service import AccessGrantService
from apps.crm.services.crm_entity_access_service import CrmEntityAccessService
from apps.crm.services.namespace_notification_recipients import (
    resolve_user_ids_for_namespace_broadcast,
)
from core.authz import AuthzRelation, AuthzService, AuthzSubject
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.identity.company_membership import set_company_member_roles
from core.models.identity_models import Company, User
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401


async def _seed_company_users(
    crm_container,
    authz_service: AuthzService,
    *,
    company_id: str,
    owner_id: str,
    member_id: str,
) -> Company:
    company_repository = crm_container.company_repository
    user_repository = crm_container.user_repository
    company = Company(
        company_id=company_id,
        name="CRM Grants",
        subdomain=f"grants-{company_id}",
        members={},
    )
    owner = User(user_id=owner_id, name="Owner", companies={})
    member = User(user_id=member_id, name="Member", companies={})
    _ = await company_repository.set(company)
    _ = await user_repository.set(owner)
    _ = await user_repository.set(member)
    _ = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=owner,
        roles=["owner"],
    )
    company = await company_repository.get(company_id)
    assert company is not None
    _ = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=member,
        roles=["member"],
    )
    company = await company_repository.get(company_id)
    assert company is not None
    return company


@pytest.mark.asyncio
async def test_share_requires_can_share(
    authz_service: AuthzService,
    crm_container,
    unique_id: str,
) -> None:
    company_id = f"co-share-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    stranger_id = f"stranger-{unique_id}"
    namespace = f"ns-{unique_id}"
    entity_id = f"ent-{unique_id}"

    _ = await _seed_company_users(
        crm_container,
        authz_service,
        company_id=company_id,
        owner_id=owner_id,
        member_id=member_id,
    )
    entity = CRMEntity(
        entity_id=entity_id,
        company_id=company_id,
        namespace=namespace,
        entity_type="note",
        name="Shared",
        user_id=owner_id,
    )
    _ = await crm_container.entity_repository.create(entity)
    access = CrmEntityAccessService(
        entity_type_repo=crm_container.entity_type_repository,
        authz=authz_service,
    )
    await access.sync_entity_created(entity)

    grants = AccessGrantService(
        entity_repo=crm_container.entity_repository,
        authz=authz_service,
    )
    with pytest.raises(AuthzDenied):
        await grants.grant_entity_to_user(
            entity_id=entity_id,
            target_user_id=stranger_id,
            role="viewer",
            created_by=stranger_id,
        )

    response = await grants.grant_entity_to_user(
        entity_id=entity_id,
        target_user_id=stranger_id,
        role="viewer",
        created_by=owner_id,
    )
    assert response.grant_type == "user"
    assert response.target_user_id == stranger_id
    listed = await grants.list_grants("entity", entity_id)
    assert any(item.target_user_id == stranger_id for item in listed)


@pytest.mark.asyncio
async def test_public_projection_via_fga_list_users(
    authz_service: AuthzService,
    crm_container,
    unique_id: str,
) -> None:
    company_id = f"co-pub-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    namespace = f"ns-{unique_id}"
    entity_id = f"ent-{unique_id}"

    _ = await _seed_company_users(
        crm_container,
        authz_service,
        company_id=company_id,
        owner_id=owner_id,
        member_id=member_id,
    )
    entity = CRMEntity(
        entity_id=entity_id,
        company_id=company_id,
        namespace=namespace,
        entity_type="note",
        name="Public note",
        description="secret body",
        user_id=owner_id,
    )
    _ = await crm_container.entity_repository.create(entity)
    access = CrmEntityAccessService(
        entity_type_repo=crm_container.entity_type_repository,
        authz=authz_service,
    )
    await access.sync_entity_created(entity)
    grants = AccessGrantService(
        entity_repo=crm_container.entity_repository,
        authz=authz_service,
    )
    _ = await grants.grant_entity_public(entity_id, created_by=owner_id)

    filtered = await access.filter_fields(entity, user_id=None, company_id=None)
    assert isinstance(filtered, dict)
    assert filtered.get("entity_id") == entity_id

    full = await access.filter_fields(entity, user_id=member_id, company_id=company_id)
    assert isinstance(full, CRMEntity)


@pytest.mark.asyncio
async def test_namespace_recipients_via_list_users(
    authz_service: AuthzService,
    crm_container,
    unique_id: str,
) -> None:
    company_id = f"co-rec-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    namespace = f"ns-{unique_id}"

    _ = await _seed_company_users(
        crm_container,
        authz_service,
        company_id=company_id,
        owner_id=owner_id,
        member_id=member_id,
    )
    from apps.crm.authz.tuples import (
        crm_namespace_company_editor_tuple,
        crm_namespace_company_link,
        crm_namespace_company_viewer_tuple,
    )

    await authz_service.write(
        [
            crm_namespace_company_link(company_id, namespace),
            crm_namespace_company_viewer_tuple(company_id, namespace),
            crm_namespace_company_editor_tuple(company_id, namespace),
        ]
    )

    recipients = await resolve_user_ids_for_namespace_broadcast(
        company_id=company_id,
        namespace=namespace,
        authz=authz_service,
    )
    assert owner_id in recipients
    assert member_id in recipients
    assert await authz_service.check(
        AuthzSubject.user(member_id),
        AuthzRelation.CAN_VIEW,
        AuthzObject.crm_namespace(company_id, namespace),
    )
