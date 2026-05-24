"""
API platform-tracing на frontend: доступ system, список spans, курсор, trace.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.tracing.models import TraceSpanWrite


@pytest_asyncio.fixture
async def frontend_client_system(frontend_app, auth_token_system):
    async with AsyncClient(
        transport=ASGITransport(app=frontend_app),
        base_url="http://testserver",
        cookies={"auth_token": auth_token_system},
        follow_redirects=True,
    ) as client:
        yield client


def _span_payload(
    *,
    span_id: str,
    trace_id: str,
    service_name: str,
    operation_name: str,
    start_time: datetime,
    company_id: str = "system",
) -> TraceSpanWrite:
    return TraceSpanWrite(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=None,
        operation_name=operation_name,
        kind="INTERNAL",
        start_time=start_time,
        end_time=start_time,
        duration_ms=0,
        status="OK",
        service_name=service_name,
        company_id=company_id,
        namespace="default",
        user_id=None,
        user_name=None,
        user_groups=None,
        session_auth=None,
        session_agent=None,
        channel=None,
        event_type=None,
        resource_type=None,
        resource_id=None,
        attributes={},
        events=[],
    )


@pytest.mark.asyncio
async def test_platform_tracing_spans_forbidden_non_system(
    frontend_client_with_auth,
):
    response = await frontend_client_with_auth.get("/frontend/api/platform-tracing/spans")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_platform_tracing_spans_unauthorized(frontend_client):
    response = await frontend_client.get("/frontend/api/platform-tracing/spans")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_platform_tracing_substring_query_too_short_returns_422(
    frontend_client_system,
):
    response = await frontend_client_system.get(
        "/frontend/api/platform-tracing/spans",
        params={"company_id_query": "a"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_platform_tracing_spans_system_filters_and_cursor(
    frontend_client_system,
    frontend_container,
    unique_id: str,
):
    repo = frontend_container.span_repository
    svc = f"adm_{unique_id}"
    tid = f"tr_{unique_id}"
    base = datetime.now(timezone.utc)
    op = f"op.admin.{unique_id}"
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_s1",
            trace_id=tid,
            service_name=svc,
            operation_name=op,
            start_time=base + timedelta(seconds=2),
        )
    )
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_s2",
            trace_id=tid,
            service_name=svc,
            operation_name=op,
            start_time=base,
        )
    )

    r1 = await frontend_client_system.get(
        "/frontend/api/platform-tracing/spans",
        params={
            "service_name": svc,
            "company_id": "system",
            "limit": 1,
        },
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert len(body1["items"]) == 1
    assert body1["items"][0]["operation_name"] == op
    assert "company_name" in body1["items"][0]
    assert "user_display_name" in body1["items"][0]
    assert body1["next_cursor"]

    r2 = await frontend_client_system.get(
        "/frontend/api/platform-tracing/spans",
        params={
            "service_name": svc,
            "company_id": "system",
            "limit": 1,
            "cursor": body1["next_cursor"],
        },
    )
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2["items"]) == 1
    assert body2["items"][0]["span_id"] != body1["items"][0]["span_id"]


@pytest.mark.asyncio
async def test_platform_tracing_trace_tree(
    frontend_client_system,
    frontend_container,
    unique_id: str,
):
    repo = frontend_container.span_repository
    tid = f"tree_{unique_id}"
    t0 = datetime.now(timezone.utc)
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_root",
            trace_id=tid,
            service_name=f"svc_{unique_id}",
            operation_name="root",
            start_time=t0,
        )
    )
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_child",
            trace_id=tid,
            service_name=f"svc_{unique_id}",
            operation_name="child",
            start_time=t0 + timedelta(microseconds=1),
        ).model_copy(update={"parent_span_id": f"{unique_id}_root"})
    )

    response = await frontend_client_system.get(
        f"/frontend/api/platform-tracing/traces/{tid}",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"] == tid
    assert data["spans_count"] == 2
    tree = data["tree"]
    assert len(tree) == 1
    assert tree[0]["span_id"] == f"{unique_id}_root"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["span_id"] == f"{unique_id}_child"


@pytest.mark.asyncio
async def test_platform_tracing_facet_users_scoped_by_company(
    frontend_client_system,
    frontend_container,
    unique_id: str,
):
    repo = frontend_container.span_repository
    base = datetime.now(timezone.utc)
    co_x = f"api_co_x_{unique_id}"
    uid_x = f"api_user_{unique_id}"
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_fx",
            trace_id=f"{unique_id}_tfx",
            service_name=f"svc_{unique_id}",
            operation_name="fx",
            start_time=base,
            company_id=co_x,
        ).model_copy(update={"user_id": uid_x}),
    )
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_fy",
            trace_id=f"{unique_id}_tfy",
            service_name=f"svc_{unique_id}",
            operation_name="fy",
            start_time=base,
            company_id="system",
        ).model_copy(update={"user_id": uid_x}),
    )
    r = await frontend_client_system.get(
        "/frontend/api/platform-tracing/facets/users",
        params={"q": unique_id, "company_id": co_x},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    values = {x["value"] for x in items}
    assert uid_x in values
    r2 = await frontend_client_system.get(
        "/frontend/api/platform-tracing/facets/users",
        params={"q": unique_id, "company_id": co_x, "namespace": "nope"},
    )
    assert r2.status_code == 200
    values2 = {x["value"] for x in r2.json()["items"]}
    assert uid_x not in values2


@pytest.mark.asyncio
async def test_platform_tracing_facet_users_finds_by_email_and_label(
    frontend_client_system,
    frontend_container,
    unique_id: str,
) -> None:
    from core.models.identity_models import User

    local_part = f"tracemail-{unique_id}"
    email = f"{local_part}@facet.test"
    uid = f"u_no_user_token_{unique_id}"
    user = User(
        user_id=uid,
        name=f"Facet By Mail {unique_id}",
        emails=[email],
    )
    await frontend_container.user_repository.set(user)
    repo = frontend_container.span_repository
    base = datetime.now(timezone.utc)
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_em",
            trace_id=f"{unique_id}_tem",
            service_name=f"svc_{unique_id}",
            operation_name="em",
            start_time=base,
        ).model_copy(update={"user_id": uid}),
    )
    r = await frontend_client_system.get(
        "/frontend/api/platform-tracing/facets/users",
        params={"q": local_part, "limit": 20},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    found = next((x for x in items if x["value"] == uid), None)
    assert found is not None
    assert "·" in found["label"] or "@" in found["label"]


@pytest.mark.asyncio
async def test_platform_tracing_spans_resolve_user_id_query_email(
    frontend_client_system,
    frontend_container,
    unique_id: str,
) -> None:
    from core.models.identity_models import User

    email = f"spanres-{unique_id}@u.test"
    uid = f"u_spanres_{unique_id}"
    await frontend_container.user_repository.set(
        User(
            user_id=uid,
            name="Span Res User",
            emails=[email],
        )
    )
    repo = frontend_container.span_repository
    base = datetime.now(timezone.utc)
    sid = f"{unique_id}_uresem"
    await repo.save_span(
        _span_payload(
            span_id=sid,
            trace_id=f"{unique_id}_turesem",
            service_name="svc3",
            operation_name="op3",
            start_time=base,
        ).model_copy(update={"user_id": uid}),
    )
    r = await frontend_client_system.get(
        "/frontend/api/platform-tracing/spans",
        params={"user_id_query": email, "limit": 20},
    )
    assert r.status_code == 200
    ids = {x["span_id"] for x in r.json()["items"]}
    assert sid in ids


@pytest.mark.asyncio
async def test_platform_tracing_spans_namespace_and_service_query(
    frontend_client_system,
    frontend_container,
    unique_id: str,
):
    repo = frontend_container.span_repository
    base = datetime.now(timezone.utc)
    ns = f"api_ns_{unique_id}"
    svc = f"api_svc_{unique_id}_z"
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_nq",
            trace_id=f"{unique_id}_tnq",
            service_name=svc,
            operation_name="nq",
            start_time=base,
        ).model_copy(update={"namespace": ns})
    )
    r = await frontend_client_system.get(
        "/frontend/api/platform-tracing/spans",
        params={"namespace_query": unique_id, "limit": 20},
    )
    assert r.status_code == 200
    ids = {x["span_id"] for x in r.json()["items"]}
    assert f"{unique_id}_nq" in ids
    r2 = await frontend_client_system.get(
        "/frontend/api/platform-tracing/spans",
        params={"service_name_query": unique_id, "limit": 20},
    )
    assert r2.status_code == 200
    ids2 = {x["span_id"] for x in r2.json()["items"]}
    assert f"{unique_id}_nq" in ids2


@pytest.mark.asyncio
async def test_platform_tracing_facet_companies_by_subdomain(
    frontend_client_system,
    frontend_container,
    unique_id: str,
) -> None:
    from core.models.identity_models import Company, TariffPlan

    repo = frontend_container.span_repository
    cid = f"co_subfacet_{unique_id}"
    sub = f"subfacet-{unique_id}"
    co = Company(
        company_id=cid,
        name=f"NameSub {unique_id}",
        subdomain=sub,
        members={},
        status="active",
        tariff_plan=TariffPlan.FREE,
    )
    await frontend_container.company_repository.set(co)

    base = datetime.now(timezone.utc)
    await repo.save_span(
        _span_payload(
            span_id=f"{unique_id}_sub",
            trace_id=f"{unique_id}_tsub",
            service_name="svc",
            operation_name="op",
            start_time=base,
            company_id=cid,
        )
    )
    r = await frontend_client_system.get(
        "/frontend/api/platform-tracing/facets/companies",
        params={"q": sub, "limit": 20},
    )
    assert r.status_code == 200
    values = {x["value"] for x in r.json()["items"]}
    assert cid in values


@pytest.mark.asyncio
async def test_platform_tracing_spans_resolve_company_id_query_subdomain(
    frontend_client_system,
    frontend_container,
    unique_id: str,
) -> None:
    from core.models.identity_models import Company, TariffPlan

    repo = frontend_container.span_repository
    cid = f"co_sresolve_{unique_id}"
    sub = f"sres-{unique_id}"
    co = Company(
        company_id=cid,
        name=f"Res Co {unique_id}",
        subdomain=sub,
        members={},
        status="active",
        tariff_plan=TariffPlan.FREE,
    )
    await frontend_container.company_repository.set(co)

    base = datetime.now(timezone.utc)
    sid = f"{unique_id}_sp_res"
    await repo.save_span(
        _span_payload(
            span_id=sid,
            trace_id=f"{unique_id}_tres",
            service_name="svc2",
            operation_name="op2",
            start_time=base,
            company_id=cid,
        )
    )
    r = await frontend_client_system.get(
        "/frontend/api/platform-tracing/spans",
        params={"company_id_query": sub, "limit": 20},
    )
    assert r.status_code == 200
    ids = {x["span_id"] for x in r.json()["items"]}
    assert sid in ids
