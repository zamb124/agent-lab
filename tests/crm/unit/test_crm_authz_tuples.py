"""Тесты CRM authz tuple builders (без OpenFGA I/O)."""

from apps.crm.authz import (
    crm_entity_namespace_link,
    crm_entity_owner_tuple,
    crm_grant_tuple,
    crm_namespace_company_editor_tuple,
    crm_namespace_company_link,
    crm_namespace_company_viewer_tuple,
)
from core.authz.types import AuthzRelation


def test_crm_entity_owner_tuple() -> None:
    item = crm_entity_owner_tuple("e1", "u1")
    assert item.relation is AuthzRelation.OWNER
    assert item.obj.fga_id == "crm_entity:e1"
    assert item.subject.fga_user == "user:u1"


def test_crm_namespace_links() -> None:
    ns_link = crm_namespace_company_link("acme", "default")
    assert ns_link.relation is AuthzRelation.COMPANY
    assert ns_link.obj.fga_id == "crm_namespace:acme/default"
    assert ns_link.subject.fga_user == "company:acme"

    viewer = crm_namespace_company_viewer_tuple("acme", "default")
    assert viewer.relation is AuthzRelation.VIEWER
    assert viewer.subject.fga_user == "company:acme#member"
    editor = crm_namespace_company_editor_tuple("acme", "default")
    assert editor.relation is AuthzRelation.EDITOR
    assert editor.subject.fga_user == "company:acme#member"

    ent_link = crm_entity_namespace_link("e1", "acme", "default")
    assert ent_link.relation is AuthzRelation.NAMESPACE
    assert ent_link.subject.fga_user == "crm_namespace:acme/default"


def test_crm_grant_tuple_variants() -> None:
    public = crm_grant_tuple(
        resource_type="entity",
        resource_id="e1",
        resource_company_id="acme",
        grant_type="public",
        role="viewer",
        target_user_id=None,
        target_company_id=None,
    )
    assert public.subject.fga_user == "user:*"

    user = crm_grant_tuple(
        resource_type="entity",
        resource_id="e1",
        resource_company_id="acme",
        grant_type="user",
        role="editor",
        target_user_id="u2",
        target_company_id=None,
    )
    assert user.subject.fga_user == "user:u2"
    assert user.relation is AuthzRelation.EDITOR

    company = crm_grant_tuple(
        resource_type="namespace",
        resource_id="default",
        resource_company_id="acme",
        grant_type="company",
        role="viewer",
        target_user_id=None,
        target_company_id="other",
    )
    assert company.obj.fga_id == "crm_namespace:acme/default"
    assert company.subject.fga_user == "company:other#member"
