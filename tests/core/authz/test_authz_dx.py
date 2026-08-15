"""DX sugar: can_*/require_can_* / require_company_admin."""

from __future__ import annotations

import pytest

from apps.crm.authz.tuples import (
    crm_entity_namespace_link,
    crm_entity_owner_tuple,
    crm_grant_tuple,
    crm_namespace_company_editor_tuple,
    crm_namespace_company_link,
    crm_namespace_company_viewer_tuple,
)
from core.authz import AuthzDenied, AuthzObject, AuthzService, AuthzUnavailable
from core.authz.company_sync import sync_company_member_roles
from core.context import clear_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User


@pytest.mark.asyncio
async def test_can_view_uses_context_user(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-dx-{unique_id}"
    user_id = f"u-dx-{unique_id}"
    entity_id = f"ent-dx-{unique_id}"
    namespace = f"ns-dx-{unique_id}"

    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=user_id, roles=["member"]
    )
    await authz_service.write(
        [
            crm_namespace_company_link(company_id, namespace),
            crm_namespace_company_viewer_tuple(company_id, namespace),
            crm_namespace_company_editor_tuple(company_id, namespace),
            crm_entity_owner_tuple(entity_id, f"owner-{unique_id}"),
            crm_entity_namespace_link(entity_id, company_id, namespace),
        ]
    )

    set_context(
        Context(
            user=User(user_id=user_id, name="DX"),
            active_company=Company(
                company_id=company_id,
                name="DX Co",
                subdomain=f"dx-{unique_id}",
                members={user_id: ["member"]},
            ),
            channel="api",
        )
    )
    try:
        assert await authz_service.can_view(AuthzObject.crm_entity(entity_id)) is True
        await authz_service.require_can_view(AuthzObject.crm_entity(entity_id))
        with pytest.raises(AuthzDenied):
            await authz_service.require_company_admin(company_id=company_id)
        await sync_company_member_roles(
            authz_service, company_id=company_id, user_id=user_id, roles=["admin"]
        )
        await authz_service.require_company_admin(company_id=company_id)
    finally:
        clear_context()


@pytest.mark.asyncio
async def test_can_view_public_without_context(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    entity_id = f"pub-dx-{unique_id}"
    await authz_service.write(
        [
            crm_grant_tuple(
                resource_type="entity",
                resource_id=entity_id,
                resource_company_id=f"co-{unique_id}",
                grant_type="public",
                role="viewer",
                target_user_id=None,
                target_company_id=None,
            )
        ]
    )
    clear_context()
    assert await authz_service.can_view(AuthzObject.crm_entity(entity_id)) is True
    with pytest.raises(AuthzUnavailable):
        await authz_service.can_edit(AuthzObject.crm_entity(entity_id))
