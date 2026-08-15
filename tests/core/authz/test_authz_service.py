"""Unit + integration тесты core.authz против реального OpenFGA (docker-compose-test)."""

from __future__ import annotations

import pytest

from core.authz import (
    AuthzCheckItem,
    AuthzDenied,
    AuthzObject,
    AuthzRelation,
    AuthzService,
    AuthzSubject,
    AuthzUnavailable,
)
from core.authz.company_sync import (
    company_role_tuples,
    remove_company_member,
    sync_company_member_roles,
)
from core.authz.errors import AuthzConfigError
from core.authz.ids import (
    PUBLIC_USER,
    format_namespace_key,
    format_object_id,
    format_user_id,
    parse_namespace_key,
    parse_object_id,
)
from core.authz.types import AuthzObjectType


@pytest.mark.asyncio
async def test_format_and_parse_object_ids() -> None:
    raw = format_object_id(AuthzObjectType.CRM_ENTITY, "e1")
    assert raw == "crm_entity:e1"
    object_type, key = parse_object_id(raw)
    assert object_type is AuthzObjectType.CRM_ENTITY
    assert key == "e1"
    assert format_user_id("u1") == "user:u1"
    assert format_namespace_key("acme", "default") == "acme/default"
    assert format_namespace_key("acme", "idx_x:ns") == "acme/idx_x%3Ans"
    assert parse_namespace_key("acme/idx_x%3Ans") == ("acme", "idx_x:ns")
    assert (
        format_object_id(AuthzObjectType.TOOL, "mcp:search:meta_web_search")
        == "tool:mcp%3Asearch%3Ameta_web_search"
    )
    assert parse_object_id("tool:mcp%3Asearch%3Ameta_web_search") == (
        AuthzObjectType.TOOL,
        "mcp:search:meta_web_search",
    )
    assert PUBLIC_USER == "user:*"


@pytest.mark.asyncio
async def test_parse_object_id_rejects_unknown_type() -> None:
    with pytest.raises(AuthzConfigError):
        parse_object_id("unknown_type:x")


@pytest.mark.asyncio
async def test_authz_subject_fga_user_shapes() -> None:
    assert AuthzSubject.user("alice").fga_user == "user:alice"
    assert AuthzSubject.public().fga_user == "user:*"
    assert AuthzSubject.company_member("acme").fga_user == "company:acme#member"
    assert AuthzSubject.group_member("admin").fga_user == "group:admin#member"
    ns = AuthzObject.crm_namespace("acme", "default")
    assert AuthzSubject.object_ref(ns).fga_user == "crm_namespace:acme/default"


@pytest.mark.asyncio
async def test_company_role_tuples_owner_implies_written_owner(
    unique_id: str,
) -> None:
    tuples = company_role_tuples(f"co-{unique_id}", f"u-{unique_id}", ["owner", "admin"])
    relations = {item.relation for item in tuples}
    assert AuthzRelation.OWNER in relations
    assert AuthzRelation.ADMIN in relations
    assert AuthzRelation.MEMBER in relations


@pytest.mark.asyncio
async def test_check_require_write_delete_company_member(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-{unique_id}"
    user_id = f"u-{unique_id}"
    obj = AuthzObject.company(company_id)
    subject = AuthzSubject.user(user_id)

    assert await authz_service.check(subject, AuthzRelation.OWNER, obj) is False

    await sync_company_member_roles(
        authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=["owner"],
    )
    assert await authz_service.check(subject, AuthzRelation.OWNER, obj) is True
    assert await authz_service.check(subject, AuthzRelation.ADMIN, obj) is True
    assert await authz_service.check(subject, AuthzRelation.MEMBER, obj) is True
    assert await authz_service.check(subject, AuthzRelation.CAN_ADMIN, obj) is True
    await authz_service.require(subject, AuthzRelation.CAN_ADMIN, obj)

    await remove_company_member(
        authz_service, company_id=company_id, user_id=user_id
    )
    assert await authz_service.check(subject, AuthzRelation.MEMBER, obj) is False
    with pytest.raises(AuthzDenied):
        await authz_service.require(subject, AuthzRelation.CAN_ADMIN, obj)


@pytest.mark.asyncio
async def test_developer_and_viewer_roles_grant_company_can_view(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-dev-{unique_id}"
    developer_id = f"dev-{unique_id}"
    viewer_id = f"view-{unique_id}"
    obj = AuthzObject.company(company_id)
    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=developer_id, roles=["developer"]
    )
    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=viewer_id, roles=["viewer"]
    )
    assert await authz_service.check(
        AuthzSubject.user(developer_id), AuthzRelation.CAN_VIEW, obj
    )
    assert await authz_service.check(
        AuthzSubject.user(viewer_id), AuthzRelation.CAN_VIEW, obj
    )
    assert (
        await authz_service.check(
            AuthzSubject.user(developer_id), AuthzRelation.CAN_ADMIN, obj
        )
        is False
    )


@pytest.mark.asyncio
async def test_batch_check_and_list_objects(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-batch-{unique_id}"
    user_a = f"ua-{unique_id}"
    user_b = f"ub-{unique_id}"
    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=user_a, roles=["member"]
    )
    obj = AuthzObject.company(company_id)
    items = [
        AuthzCheckItem(
            subject=AuthzSubject.user(user_a),
            relation=AuthzRelation.MEMBER,
            obj=obj,
            correlation_id="a",
        ),
        AuthzCheckItem(
            subject=AuthzSubject.user(user_b),
            relation=AuthzRelation.MEMBER,
            obj=obj,
            correlation_id="b",
        ),
    ]
    allowed = await authz_service.batch_check(items)
    assert allowed == [True, False]

    objects = await authz_service.list_objects(
        AuthzSubject.user(user_a),
        AuthzRelation.MEMBER,
        AuthzObjectType.COMPANY,
    )
    assert obj.fga_id in {item.fga_id for item in objects}


@pytest.mark.asyncio
async def test_crm_entity_inheritance_via_namespace_and_company(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    """Model: company member → crm_namespace editor → crm_entity can_edit via TTU."""
    from apps.crm.authz import (
        crm_entity_namespace_link,
        crm_entity_owner_tuple,
        crm_namespace_company_editor_tuple,
        crm_namespace_company_link,
        crm_namespace_company_viewer_tuple,
    )

    company_id = f"co-crm-{unique_id}"
    namespace = f"ns-{unique_id}"
    entity_id = f"ent-{unique_id}"
    owner_id = f"owner-{unique_id}"
    member_id = f"member-{unique_id}"

    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=member_id, roles=["member"]
    )
    await authz_service.write(
        [
            crm_namespace_company_link(company_id, namespace),
            crm_namespace_company_viewer_tuple(company_id, namespace),
            crm_namespace_company_editor_tuple(company_id, namespace),
            crm_entity_owner_tuple(entity_id, owner_id),
            crm_entity_namespace_link(entity_id, company_id, namespace),
        ]
    )

    entity = AuthzObject.crm_entity(entity_id)
    assert (
        await authz_service.check(
            AuthzSubject.user(owner_id), AuthzRelation.CAN_ADMIN, entity
        )
        is True
    )
    assert (
        await authz_service.check(
            AuthzSubject.user(member_id), AuthzRelation.CAN_EDIT, entity
        )
        is True
    )
    assert (
        await authz_service.check(
            AuthzSubject.user(f"stranger-{unique_id}"),
            AuthzRelation.CAN_VIEW,
            entity,
        )
        is False
    )


@pytest.mark.asyncio
async def test_public_viewer_on_entity_not_editor(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    from apps.crm.authz import crm_grant_tuple

    entity_id = f"pub-{unique_id}"
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
    entity = AuthzObject.crm_entity(entity_id)
    assert (
        await authz_service.check(
            AuthzSubject.public(), AuthzRelation.CAN_VIEW, entity
        )
        is True
    )
    assert (
        await authz_service.check(
            AuthzSubject.user(f"anon-{unique_id}"),
            AuthzRelation.CAN_VIEW,
            entity,
        )
        is True
    )
    assert (
        await authz_service.check(
            AuthzSubject.user(f"anon-{unique_id}"),
            AuthzRelation.CAN_EDIT,
            entity,
        )
        is False
    )


@pytest.mark.asyncio
async def test_disabled_authz_raises_unavailable(unique_id: str) -> None:
    from core.authz.client import OpenFgaAuthzClient
    from core.authz.service import AuthzService as AuthzServiceCls

    client = OpenFgaAuthzClient(
        api_url="http://127.0.0.1:9093",
        store_id="unused",
        authorization_model_id="unused",
        api_token=None,
        timeout_ms=1000,
    )
    service = AuthzServiceCls(
        client,
        enabled=False,
    )
    with pytest.raises(AuthzUnavailable):
        await service.check(
            AuthzSubject.user(f"u-{unique_id}"),
            AuthzRelation.CAN_VIEW,
            AuthzObject.crm_entity(f"e-{unique_id}"),
        )
    await service.close()
