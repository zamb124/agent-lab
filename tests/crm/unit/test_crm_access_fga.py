"""CRM CrmEntityAccessService: PDP только через OpenFGA."""

from __future__ import annotations

import pytest

from apps.crm.db.models import CRMEntity
from apps.crm.services.crm_entity_access_service import CrmEntityAccessService
from core.authz import AuthzRelation, AuthzService, AuthzSubject
from core.authz.company_sync import sync_company_member_roles
from core.authz.models import AuthzObject
from core.identity.company_membership import set_company_member_roles
from core.models.identity_models import Company, User


@pytest.mark.asyncio
async def test_owner_and_company_member_can_view_via_fga(
    authz_service: AuthzService,
    crm_container,
    unique_id: str,
) -> None:
    company_id = f"co-crm-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"
    stranger_id = f"stranger-{unique_id}"
    namespace = f"ns-{unique_id}"
    entity_id = f"ent-{unique_id}"

    company_repository = crm_container.company_repository
    user_repository = crm_container.user_repository
    company = Company(
        company_id=company_id,
        name="CRM Authz",
        subdomain=f"crm-{unique_id}",
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

    access = CrmEntityAccessService(
        entity_type_repo=crm_container.entity_type_repository,
        authz=authz_service,
    )
    entity = CRMEntity(
        entity_id=entity_id,
        company_id=company_id,
        namespace=namespace,
        entity_type="note",
        name="Secret",
        user_id=owner_id,
    )
    await access.sync_entity_created(entity)

    obj = AuthzObject.crm_entity(entity_id)
    assert await authz_service.can_view(obj, user_id=owner_id) is True
    assert await authz_service.can_edit(obj, user_id=owner_id) is True
    assert await authz_service.can_view(obj, user_id=member_id) is True
    assert await authz_service.can_edit(obj, user_id=member_id) is True
    assert await authz_service.can_view(obj, user_id=stranger_id) is False

    from apps.crm.authz.tuples import crm_grant_tuple

    await authz_service.write(
        [
            crm_grant_tuple(
                resource_type="entity",
                resource_id=entity_id,
                resource_company_id=company_id,
                grant_type="user",
                role="viewer",
                target_user_id=stranger_id,
                target_company_id=None,
            )
        ]
    )
    assert await authz_service.can_view(obj, user_id=stranger_id) is True
    assert await authz_service.can_edit(obj, user_id=stranger_id) is False

    assert await authz_service.check(
        AuthzSubject.user(member_id),
        AuthzRelation.CAN_VIEW,
        AuthzObject.crm_entity(entity_id),
    )


@pytest.mark.asyncio
async def test_sync_company_member_roles_required_for_namespace_ttu(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-ttu-{unique_id}"
    user_id = f"u-ttu-{unique_id}"
    entity_id = f"ent-ttu-{unique_id}"
    namespace = f"ns-ttu-{unique_id}"

    from apps.crm.authz.tuples import (
        crm_entity_namespace_link,
        crm_entity_owner_tuple,
        crm_namespace_company_editor_tuple,
        crm_namespace_company_link,
        crm_namespace_company_viewer_tuple,
    )

    await authz_service.write(
        [
            crm_namespace_company_link(company_id, namespace),
            crm_namespace_company_viewer_tuple(company_id, namespace),
            crm_namespace_company_editor_tuple(company_id, namespace),
            crm_entity_owner_tuple(entity_id, f"other-{unique_id}"),
            crm_entity_namespace_link(entity_id, company_id, namespace),
        ]
    )
    assert (
        await authz_service.check(
            AuthzSubject.user(user_id),
            AuthzRelation.CAN_VIEW,
            AuthzObject.crm_entity(entity_id),
        )
        is False
    )
    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=user_id, roles=["member"]
    )
    assert await authz_service.check(
        AuthzSubject.user(user_id),
        AuthzRelation.CAN_VIEW,
        AuthzObject.crm_entity(entity_id),
    )
