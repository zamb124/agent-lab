from __future__ import annotations

from core.authz.ids import format_namespace_key
from core.authz.types import AuthzObjectType, AuthzRelation
from core.datasources.authz.tuples import (
    datasource_company_link,
    datasource_company_viewer_tuple,
    datasource_owner_tuple,
    datasource_platform_link,
)


def test_datasource_tuple_object_keys() -> None:
    company_id = "acme"
    datasource_id = "ds_1"
    owner = datasource_owner_tuple(datasource_id, "user-1", company_id=company_id)
    assert owner.obj.object_type is AuthzObjectType.DATASOURCE
    assert owner.relation is AuthzRelation.OWNER
    assert owner.obj.object_key == format_namespace_key(company_id, datasource_id)

    company = datasource_company_link(datasource_id, company_id)
    assert company.relation is AuthzRelation.COMPANY

    platform = datasource_platform_link(datasource_id, company_id=company_id)
    assert platform.relation is AuthzRelation.PLATFORM

    viewer = datasource_company_viewer_tuple(datasource_id, company_id)
    assert viewer.relation is AuthzRelation.VIEWER
