"""Create-path dual-write: FGA fail → SQL row не остаётся."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from apps.crm.db.models import EntityType
from core.authz.errors import AuthzUnavailable
from core.authz.models import AuthzTuple
from core.authz.service import AuthzService
from core.context import clear_context, set_context
from core.identity.company_membership import set_company_member_roles
from core.models.context_models import Context
from core.models.identity_models import Company, Namespace, NamespaceKind, User

pytestmark = pytest.mark.asyncio


async def test_create_entity_compensate_deletes_row_when_fga_write_fails(
    authz_service: AuthzService,
    crm_container,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = f"co-cmp-{unique_id}"
    owner_id = f"owner-{unique_id}"
    namespace = f"ns-{unique_id}"
    note_name = f"Compensate {unique_id}"

    company_repository = crm_container.company_repository
    user_repository = crm_container.user_repository
    company = Company(
        company_id=company_id,
        name="CRM Compensate",
        subdomain=f"cmp-{unique_id}",
        members={},
    )
    owner = User(user_id=owner_id, name="Owner", companies={})
    _ = await company_repository.set(company)
    _ = await user_repository.set(owner)
    _ = await set_company_member_roles(
        company_repository=company_repository,
        user_repository=user_repository,
        authz=authz_service,
        company=company,
        user=owner,
        roles=["owner"],
    )

    set_context(
        Context(
            user=owner,
            active_company=company,
            channel="api",
            active_namespace=namespace,
        )
    )
    try:
        _ = await crm_container.namespace_service.save(
            Namespace(
                name=namespace,
                company_id=company_id,
                kind=NamespaceKind.COMPANY_WORKSPACE,
            )
        )
        _ = await crm_container.namespace_service.ensure_exists(namespace)
        _ = await crm_container.entity_type_repository.create_custom_type(
            EntityType(
                company_id=company_id,
                namespace=namespace,
                type_id="note",
                name="Note",
                is_system=False,
            ),
            company_id=company_id,
        )

        async def fail_write(_tuples: Sequence[AuthzTuple]) -> None:
            raise AuthzUnavailable("openfga down")

        monkeypatch.setattr(crm_container.authz_service, "write", fail_write)

        with pytest.raises(AuthzUnavailable):
            _ = await crm_container.entity_service.create_entity(
                "note",
                note_name,
                namespace=namespace,
                user_id=owner_id,
            )

        rows, _, _ = await crm_container.entity_repository.list_by_cursor(
            entity_type="note",
            namespace=namespace,
            company_id=company_id,
        )
        assert rows == []
    finally:
        clear_context()
