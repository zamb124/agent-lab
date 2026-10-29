"""
admin_span_page_and_cursor и facet-методы SpanRepository.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.tracing.models import Span


def _row(
    *,
    span_id: str,
    trace_id: str,
    service_name: str,
    operation_name: str,
    start_time: datetime,
    company_id: str | None = "acme",
    user_id: str | None = "u1",
    namespace: str = "default",
    event_type: str | None = None,
) -> Span:
    return Span(
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
        namespace=namespace,
        user_id=user_id,
        user_name=None,
        user_groups=None,
        session_auth=None,
        session_agent=None,
        channel=None,
        event_type=event_type,
        resource_type=None,
        resource_id=None,
        attributes={},
        events=[],
    )


@pytest.mark.asyncio
async def test_admin_span_page_and_cursor_ilike_company(di, unique_id: str):
    base = datetime.now(timezone.utc)
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_1",
            trace_id=f"{unique_id}_t1",
            service_name=f"svc_{unique_id}",
            operation_name="x",
            start_time=base,
            company_id="prefix_acme_suffix",
        )
    )
    rows, _ = await Span.admin_span_page_and_cursor_by_start_time_and_span_id_desc(
        company_id_query="acme",
        limit=20,
    )
    ids = {r.span_id for r in rows}
    assert f"{unique_id}_1" in ids


@pytest.mark.asyncio
async def test_admin_facet_company_requires_min_len_for_ilike_branch(di, unique_id: str):
    base = datetime.now(timezone.utc)
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_f",
            trace_id=f"{unique_id}_tf",
            service_name=f"svc_{unique_id}",
            operation_name="y",
            start_time=base,
            company_id="zz_unique_facet",
        )
    )
    with pytest.raises(ValueError, match="company_id_query"):
        await Span.admin_span_page_and_cursor_by_start_time_and_span_id_desc(company_id_query="z", limit=10)


@pytest.mark.asyncio
async def test_admin_facet_distinct_company_ids(di, unique_id: str):
    base = datetime.now(timezone.utc)
    cid = f"facet_co_{unique_id}"
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_fc",
            trace_id=f"{unique_id}_tfc",
            service_name=f"svc_{unique_id}",
            operation_name="z",
            start_time=base,
            company_id=cid,
        )
    )
    out = await Span.admin_facet_distinct_company_ids(q=unique_id, limit=20)
    assert cid in out


@pytest.mark.asyncio
async def test_admin_list_distinct_company_ids_in_spans(di, unique_id: str):
    base = datetime.now(timezone.utc)
    cid = f"list_in_spans_{unique_id}"
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_lis",
            trace_id=f"{unique_id}_tlis",
            service_name=f"svc_{unique_id}",
            operation_name="z",
            start_time=base,
            company_id=cid,
        )
    )
    out = await Span.admin_list_distinct_company_ids_in_spans(max_ids=5000)
    assert cid in out


@pytest.mark.asyncio
async def test_admin_list_distinct_user_ids_in_spans(di, unique_id: str):
    base = datetime.now(timezone.utc)
    uid = f"list_users_{unique_id}"
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_uins",
            trace_id=f"{unique_id}_tuins",
            service_name=f"svc_{unique_id}",
            operation_name="z",
            start_time=base,
            user_id=uid,
        )
    )
    out = await Span.admin_list_distinct_user_ids_in_spans(max_ids=5000)
    assert uid in out


@pytest.mark.asyncio
async def test_admin_facet_distinct_user_ids_scoped_by_company(di, unique_id: str):
    base = datetime.now(timezone.utc)
    co_a = f"scope_a_{unique_id}"
    co_b = f"scope_b_{unique_id}"
    uid = f"user_scope_{unique_id}"
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_sa",
            trace_id=f"{unique_id}_tsa",
            service_name=f"svc_{unique_id}",
            operation_name="a",
            start_time=base,
            company_id=co_a,
            user_id=uid,
        )
    )
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_sb",
            trace_id=f"{unique_id}_tsb",
            service_name=f"svc_{unique_id}",
            operation_name="b",
            start_time=base,
            company_id=co_b,
            user_id=uid,
        )
    )
    out_all = await Span.admin_facet_distinct_user_ids(q=unique_id, limit=20)
    assert uid in out_all
    out_a = await Span.admin_facet_distinct_user_ids(q=unique_id, company_id=co_a, limit=20)
    assert uid in out_a
    out_b_only = await Span.admin_facet_distinct_user_ids(
        q=unique_id, company_id=co_b, namespace="other", limit=20
    )
    assert uid not in out_b_only


@pytest.mark.asyncio
async def test_admin_span_page_and_cursor_namespace_and_service_ilike(di, unique_id: str):
    base = datetime.now(timezone.utc)
    svc = f"my_svc_{unique_id}_tail"
    await Span.insert_span_once(
        _row(
            span_id=f"{unique_id}_ns",
            trace_id=f"{unique_id}_tns",
            service_name=svc,
            operation_name="op",
            start_time=base,
            company_id="system",
            namespace=f"ns_{unique_id}_x",
        )
    )
    rows_ns, _ = await Span.admin_span_page_and_cursor_by_start_time_and_span_id_desc(
        namespace_query=unique_id,
        limit=20,
    )
    assert any(r.span_id == f"{unique_id}_ns" for r in rows_ns)
    rows_svc, _ = await Span.admin_span_page_and_cursor_by_start_time_and_span_id_desc(
        service_name_query=unique_id,
        limit=20,
    )
    assert any(r.span_id == f"{unique_id}_ns" for r in rows_svc)
