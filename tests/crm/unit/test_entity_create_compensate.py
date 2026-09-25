"""Create-path dual-write: FGA fail → SQL row не остаётся."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.entity_type import EntityType
from core.authz.errors import AuthzUnavailable
from core.authz.models import AuthzTuple
from core.authz.service import AuthzService
from core.context import clear_context, set_context
from core.identity.company_membership import set_company_member_roles
from core.models.context_models import Context
from core.models.identity_models import Company, Namespace, NamespaceKind, User

pytestmark = pytest.mark.asyncio


async def test_search_similar_requires_user_context(crm_di) -> None:
    set_context(
        Context(
            user=User(user_id=" ", name="No User"),
            active_company=Company(company_id="system", name="System"),
            channel="test",
        )
    )
    try:
        with pytest.raises(ValueError, match="User context is required for CRM semantic search"):
            _ = await crm_di.entity_service.search_similar("alpha")
    finally:
        clear_context()


async def test_create_entity_compensate_deletes_row_when_fga_write_fails(
    authz_service: AuthzService,
    crm_di,
    unique_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company_id = f"co-cmp-{unique_id}"
    owner_id = f"owner-{unique_id}"
    namespace = f"ns-{unique_id}"
    note_name = f"Compensate {unique_id}"

    company = Company(
        company_id=company_id,
        name="CRM Compensate",
        subdomain=f"cmp-{unique_id}",
        members={},
    )
    owner = User(user_id=owner_id, name="Owner", companies={})
    _ = await Company.set(company)
    _ = await User.set(owner)
    _ = await set_company_member_roles(
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
        _ = await crm_di.namespace_service.save(
            Namespace(
                name=namespace,
                company_id=company_id,
                kind=NamespaceKind.COMPANY_WORKSPACE,
            )
        )
        _ = await crm_di.namespace_service.ensure_exists(namespace)
        _ = await EntityType.create(
            EntityType(
                company_id=company_id,
                namespace=namespace,
                type_id="note",
                name="Note",
                is_system=False,
            ),
        )

        async def fail_write(_tuples: Sequence[AuthzTuple]) -> None:
            raise AuthzUnavailable("openfga down")

        monkeypatch.setattr(crm_di.authz_service, "write", fail_write)

        with pytest.raises(AuthzUnavailable):
            _ = await crm_di.entity_service.create_entity(
                "note",
                note_name,
                namespace=namespace,
                user_id=owner_id,
            )

        rows = (
            await CRMEntity.cursor_page(
                entity_type="note",
                namespace=namespace,
                company_id=company_id,
            )
        ).items
        assert rows == []
    finally:
        clear_context()
