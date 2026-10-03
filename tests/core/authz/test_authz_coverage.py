"""Доп. покрытие core.authz: ids/models/factory/bootstrap/list/expand/sync edges."""

from __future__ import annotations

import pytest

from core.authz import (
    AuthzObject,
    AuthzRelation,
    AuthzService,
    AuthzSubject,
    AuthzSubjectKind,
    AuthzTuple,
    AuthzUnavailable,
)
from core.authz.bootstrap import bootstrap_openfga, load_model_payload
from core.authz.company_sync import (
    company_role_tuples,
    remove_company_member,
    sync_company_member_roles,
)
from core.authz.errors import AuthzConfigError
from core.authz.factory import build_authz_service
from core.authz.http_admin import create_store
from core.authz.ids import (
    format_company_member_userset,
    format_group_id,
    format_namespace_key,
    format_object_id,
    format_user_id,
    group_member_company_id,
    group_object_key,
    is_openfga_user_subject_id,
    parse_flow_branch_key,
    parse_object_id,
)
from core.authz.types import AuthzObjectType
from core.config.models import OpenFGAConfig


def test_openfga_write_retryable_detection() -> None:
    from openfga_sdk.exceptions import ApiException

    from core.authz.client import _is_openfga_write_retryable

    assert _is_openfga_write_retryable(ApiException(status=409, reason="conflict"))
    assert _is_openfga_write_retryable(ApiException(status=500, reason="internal"))
    assert _is_openfga_write_retryable(
        RuntimeError("transactional write failed due to conflict: Aborted")
    )
    assert not _is_openfga_write_retryable(
        ApiException(status=500, reason="Request Deadline Exceeded")
    )
    assert not _is_openfga_write_retryable(
        RuntimeError("[write] HTTP 500 Request Deadline Exceeded (deadline_exceeded)")
    )
    assert not _is_openfga_write_retryable(ApiException(status=400, reason="bad"))
    assert not _is_openfga_write_retryable(RuntimeError("unrelated"))


def test_ids_validation_edges() -> None:
    with pytest.raises(AuthzConfigError):
        format_object_id(AuthzObjectType.CRM_ENTITY, "")
    assert format_object_id(AuthzObjectType.CRM_ENTITY, "a:b") == "crm_entity:a%3Ab"
    with pytest.raises(AuthzConfigError):
        format_namespace_key("", "ns")
    with pytest.raises(AuthzConfigError):
        format_namespace_key("co", "")
    with pytest.raises(AuthzConfigError):
        format_namespace_key("co/x", "ns")
    with pytest.raises(AuthzConfigError):
        parse_object_id("nocolon")
    with pytest.raises(AuthzConfigError):
        parse_object_id("crm_entity:")
    with pytest.raises(AuthzConfigError):
        format_user_id("")
    with pytest.raises(AuthzConfigError):
        format_user_id("guest:token")
    assert is_openfga_user_subject_id("alice") is True
    assert is_openfga_user_subject_id("guest:token") is False
    assert is_openfga_user_subject_id("") is False
    with pytest.raises(AuthzConfigError):
        format_group_id("")
    with pytest.raises(AuthzConfigError):
        format_company_member_userset("")
    assert format_group_id("admins") == "group:admins"
    assert format_group_id("acme/developers") == "group:acme/developers"
    assert format_company_member_userset("acme") == "company:acme#member"
    assert group_object_key("admin") == "admin"
    assert group_object_key("developers", company_id="acme") == "acme/developers"
    assert group_member_company_id("admin", "acme") is None
    assert group_member_company_id("developers", "acme") == "acme"
    with pytest.raises(AuthzConfigError):
        group_member_company_id("developers", "")
    with pytest.raises(AuthzConfigError):
        group_member_company_id("", "acme")
    with pytest.raises(AuthzConfigError):
        group_object_key("developers")
    with pytest.raises(AuthzConfigError):
        group_object_key("admin", company_id="acme")
    with pytest.raises(AuthzConfigError):
        group_object_key("")


def test_authz_object_factories_and_subject_kinds() -> None:
    assert AuthzObject.group("admin").fga_id == "group:admin"
    assert AuthzObject.group("g1", company_id="c").fga_id == "group:c/g1"
    with pytest.raises(AuthzConfigError):
        AuthzObject.group("developers", company_id=None)
    with pytest.raises(AuthzConfigError):
        AuthzObject.group("admin", company_id="c")
    assert AuthzObject.platform().fga_id == "platform:global"
    assert AuthzObject.platform_namespace("c", "n").fga_id == "platform_namespace:c/n"
    assert AuthzObject.wiki_page("w1").fga_id == "wiki_page:w1"
    assert AuthzObject.document_catalog("cat").fga_id == "document_catalog:cat"
    assert AuthzObject.document_file("f1").fga_id == "document_file:f1"
    assert AuthzObject.sync_channel("ch").fga_id == "sync_channel:ch"
    assert AuthzObject.work_queue("q").fga_id == "work_queue:q"
    assert AuthzObject.mailbox_binding("mb").fga_id == "mailbox_binding:mb"
    assert AuthzObject.flow("flow1", company_id="c").fga_id == "flow:c/flow1"
    assert (
        AuthzObject.flow_branch("flow1", "main", company_id="c").fga_id
        == "flow_branch:c/flow1/main"
    )
    assert parse_flow_branch_key("c/flow1/main") == ("c", "flow1", "main")
    assert AuthzObject.tool("tool1", company_id="c").fga_id == "tool:c/tool1"
    assert AuthzObject.flow_ui_share("share1").fga_id == "flow_ui_share:share1"
    assert AuthzObject.agent_device("dev1").fga_id == "agent_device:dev1"
    assert AuthzObject.from_fga_id("crm_entity:e1").object_key == "e1"

    assert AuthzSubject(AuthzSubjectKind.API_KEY, "k1").fga_user == "api_key:k1"
    with pytest.raises(ValueError):
        _ = AuthzSubject(AuthzSubjectKind.OBJECT, "no-colon").fga_user


def test_company_role_tuples_unknown_role_becomes_member() -> None:
    tuples = company_role_tuples("c1", "u1", ["guest"])
    assert len(tuples) == 1
    assert tuples[0].relation is AuthzRelation.MEMBER
    empty = company_role_tuples("c1", "u1", [])
    assert empty == []


def test_company_role_tuples_product_roles_map_to_fga() -> None:
    developer = company_role_tuples("c1", "u1", ["developer"])
    assert len(developer) == 1
    assert developer[0].relation is AuthzRelation.MEMBER
    viewer = company_role_tuples("c1", "u1", ["viewer"])
    assert len(viewer) == 1
    assert viewer[0].relation is AuthzRelation.MEMBER
    mixed = {
        item.relation
        for item in company_role_tuples("c1", "u1", ["owner", "developer", "viewer"])
    }
    assert mixed == {AuthzRelation.OWNER, AuthzRelation.MEMBER}


def test_build_authz_service_enabled_flag(openfga_settings: OpenFGAConfig) -> None:
    cfg = openfga_settings.model_copy(update={"enabled": True})
    service = build_authz_service(cfg)
    assert service.enabled is True


@pytest.mark.asyncio
async def test_sync_fail_closed_when_authz_disabled(unique_id: str) -> None:
    from core.authz.client import OpenFgaAuthzClient
    from core.authz.errors import AuthzUnavailable
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
        await sync_company_member_roles(
            service, company_id=f"c-{unique_id}", user_id=f"u-{unique_id}", roles=["owner"]
        )
    with pytest.raises(AuthzUnavailable):
        await remove_company_member(
            service, company_id=f"c-{unique_id}", user_id=f"u-{unique_id}"
        )
    await service.close()


@pytest.mark.asyncio
async def test_list_tuples_by_object_type_and_subject(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    user_id = f"u-expl-{unique_id}"
    other_id = f"u-other-{unique_id}"
    page_a = f"wiki-a-{unique_id}"
    page_b = f"wiki-b-{unique_id}"
    page_c = f"wiki-c-{unique_id}"
    await authz_service.write(
        [
            AuthzTuple(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.VIEWER,
                obj=AuthzObject.wiki_page(page_a),
            ),
            AuthzTuple(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.EDITOR,
                obj=AuthzObject.wiki_page(page_b),
            ),
            AuthzTuple(
                subject=AuthzSubject.user(other_id),
                relation=AuthzRelation.VIEWER,
                obj=AuthzObject.wiki_page(page_c),
            ),
        ]
    )
    found = await authz_service.list_tuples(
        object_type=AuthzObjectType.WIKI_PAGE,
        subject=AuthzSubject.user(user_id),
    )
    assert {item.obj.object_key for item in found} == {page_a, page_b}
    assert {item.relation for item in found} == {AuthzRelation.VIEWER, AuthzRelation.EDITOR}

    from core.authz.errors import AuthzConfigError

    with pytest.raises(AuthzConfigError):
        await authz_service.list_tuples()


@pytest.mark.asyncio
async def test_list_users_expand_write_delete_empty(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    company_id = f"co-list-{unique_id}"
    user_id = f"u-list-{unique_id}"
    await authz_service.write([])
    await authz_service.delete([])
    assert await authz_service.batch_check([]) == []

    await sync_company_member_roles(
        authz_service, company_id=company_id, user_id=user_id, roles=["owner"]
    )
    obj = AuthzObject.company(company_id)
    users = await authz_service.list_users(obj, AuthzRelation.OWNER)
    assert AuthzSubject.user(user_id) in users

    tree = await authz_service.expand(obj, AuthzRelation.MEMBER)
    assert tree.obj == obj
    assert tree.relation is AuthzRelation.MEMBER
    assert tree.root.relation != "" or tree.root.users or tree.root.children

    await authz_service.write_and_delete(
        [
            AuthzTuple(
                subject=AuthzSubject.user(f"extra-{unique_id}"),
                relation=AuthzRelation.MEMBER,
                obj=obj,
            )
        ],
        [
            AuthzTuple(
                subject=AuthzSubject.user(user_id),
                relation=AuthzRelation.OWNER,
                obj=obj,
            )
        ],
    )


@pytest.mark.asyncio
async def test_bootstrap_creates_store_and_writes_model(
    openfga_settings: OpenFGAConfig,
) -> None:
    schema_version, type_definitions = load_model_payload()
    assert schema_version == "1.1"
    assert type_definitions

    store_id = await create_store(
        api_url=openfga_settings.api_url,
        name=f"platform-test-{openfga_settings.store_id[-8:]}",
        api_token=openfga_settings.api_token,
    )
    assert store_id
    resolved_store, model_id = await bootstrap_openfga(
        api_url=openfga_settings.api_url,
        api_token=openfga_settings.api_token,
        store_id=store_id,
    )
    assert resolved_store == store_id
    assert model_id


@pytest.mark.asyncio
async def test_list_users_public_and_company_member(
    authz_service: AuthzService,
    unique_id: str,
) -> None:
    from apps.crm.authz import crm_grant_tuple

    entity_id = f"lu-{unique_id}"
    company_id = f"co-lu-{unique_id}"
    await authz_service.write(
        [
            crm_grant_tuple(
                resource_type="entity",
                resource_id=entity_id,
                resource_company_id=company_id,
                grant_type="public",
                role="viewer",
                target_user_id=None,
                target_company_id=None,
            ),
            crm_grant_tuple(
                resource_type="entity",
                resource_id=entity_id,
                resource_company_id=company_id,
                grant_type="company",
                role="editor",
                target_user_id=None,
                target_company_id=company_id,
            ),
        ]
    )
    entity = AuthzObject.crm_entity(entity_id)
    viewers = await authz_service.list_users(
        entity,
        AuthzRelation.VIEWER,
        user_filters=(AuthzObjectType.USER,),
    )
    assert AuthzSubject.public() in viewers

    editors = await authz_service.list_users(
        entity,
        AuthzRelation.EDITOR,
        user_filters=(AuthzObjectType.COMPANY,),
    )
    assert AuthzSubject.company_member(company_id) in editors


@pytest.mark.asyncio
async def test_disabled_authz_service_rejects_checks(unique_id: str) -> None:
    from core.authz.client import OpenFgaAuthzClient
    from core.authz.service import AuthzService as AuthzServiceCls

    client = OpenFgaAuthzClient(
        api_url="http://127.0.0.1:9093",
        store_id="unused",
        authorization_model_id="unused",
        api_token="tok",
        timeout_ms=1000,
    )
    service = AuthzServiceCls(client, enabled=False)
    assert service.enabled is False
    with pytest.raises(AuthzUnavailable):
        await service.check(
            AuthzSubject.user(f"u-{unique_id}"),
            AuthzRelation.MEMBER,
            AuthzObject.company(f"c-{unique_id}"),
        )
    await service.close()


def test_build_authz_service_requires_store_and_model_when_enabled() -> None:
    with pytest.raises(AuthzConfigError, match="store_id"):
        _ = build_authz_service(
            OpenFGAConfig(
                enabled=True,
                api_url="http://127.0.0.1:9090",
                store_id="",
                authorization_model_id="m1",
            )
        )
    with pytest.raises(AuthzConfigError, match="authorization_model_id"):
        _ = build_authz_service(
            OpenFGAConfig(
                enabled=True,
                api_url="http://127.0.0.1:9090",
                store_id="s1",
                authorization_model_id="",
            )
        )


@pytest.mark.asyncio
async def test_bootstrap_creates_store_when_store_id_none(
    openfga_settings: OpenFGAConfig,
) -> None:
    store_id, model_id = await bootstrap_openfga(
        api_url=openfga_settings.api_url,
        api_token=openfga_settings.api_token,
        store_id=None,
    )
    assert store_id
    assert model_id


def test_bootstrap_main_cli(
    openfga_settings: OpenFGAConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.authz import bootstrap as bootstrap_mod

    async def _fake_bootstrap(**_kwargs: object) -> tuple[str, str]:
        return openfga_settings.store_id, "model-x"

    monkeypatch.setattr(bootstrap_mod, "bootstrap_openfga", _fake_bootstrap)
    assert bootstrap_mod.main([]) == 0


@pytest.mark.asyncio
async def test_client_requires_api_url() -> None:
    from core.authz.client import OpenFgaAuthzClient

    with pytest.raises(AuthzConfigError):
        OpenFgaAuthzClient(
            api_url="",
            store_id="s",
            authorization_model_id="m",
            api_token=None,
            timeout_ms=1000,
        )


@pytest.mark.asyncio
async def test_unconfigured_store_raises(unique_id: str) -> None:
    from core.authz.client import OpenFgaAuthzClient
    from core.authz.service import AuthzService as AuthzServiceCls

    client = OpenFgaAuthzClient(
        api_url="http://127.0.0.1:9093",
        store_id="",
        authorization_model_id="",
        api_token=None,
        timeout_ms=1000,
    )
    service = AuthzServiceCls(client, enabled=True)
    with pytest.raises(AuthzUnavailable):
        await service.check(
            AuthzSubject.user(f"u-{unique_id}"),
            AuthzRelation.MEMBER,
            AuthzObject.company(f"c-{unique_id}"),
        )
    await service.close()
