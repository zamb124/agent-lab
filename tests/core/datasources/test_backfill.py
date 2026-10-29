"""Datasource OpenFGA backfill is idempotent on live tuples."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from core.authz.factory import build_authz_service
from core.authz.models import AuthzObject, AuthzTuple
from core.datasources.authz.backfill import backfill_datasource_authz
from tests.fixtures.datasources import CustomerDatasource

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


def _tuple_fingerprint(item: AuthzTuple) -> tuple[str, str, str, str]:
    return (
        str(item.obj.object_type),
        item.obj.object_key,
        str(item.relation),
        item.subject.fga_user,
    )


async def test_datasource_authz_backfill_idempotent(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    stored = await flows_client.get(
        f"/flows/api/v1/datasources/{customer_datasource.datasource_id}",
        headers=auth_headers_system,
    )
    assert stored.status_code == 200, stored.text
    company_id = stored.json()["company_id"]
    if not isinstance(company_id, str) or not company_id.strip():
        raise AssertionError("datasource company_id required")

    authz = build_authz_service()
    obj = AuthzObject.datasource(
        customer_datasource.datasource_id, company_id=company_id
    )
    before = frozenset(_tuple_fingerprint(item) for item in await authz.list_tuples(obj))
    assert before

    written_first, _owners_first = await backfill_datasource_authz()
    after_first = frozenset(
        _tuple_fingerprint(item) for item in await authz.list_tuples(obj)
    )
    written_second, _owners_second = await backfill_datasource_authz()
    after_second = frozenset(
        _tuple_fingerprint(item) for item in await authz.list_tuples(obj)
    )

    assert written_first >= 1
    assert written_second >= 1
    assert after_first == before
    assert after_second == before

    still_visible = await flows_client.get(
        f"/flows/api/v1/datasources/{customer_datasource.datasource_id}",
        headers=auth_headers_system,
    )
    assert still_visible.status_code == 200, still_visible.text
