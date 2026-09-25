"""
Тесты SpanRepository: единый API для любого сервиса (service_name + операция + тип + курсор).

Персистентность — реальная БД platform_tracing (см. testing.mdc).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.tracing.models import Span


def _span_row(
    *,
    span_id: str,
    trace_id: str,
    service_name: str,
    operation_name: str,
    start_time: datetime,
    company_id: str | None = "system",
    namespace: str | None = "default",
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
        user_id=None,
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
class TestSpanRepositoryServiceQuery:
    async def test_get_returns_saved_operation(
        self,
        di,
        unique_id: str,
    ):
        sid = f"{unique_id}_op1"
        tid = f"{unique_id}_tr1"
        t0 = datetime.now(timezone.utc)
        await Span.insert_once(
            _span_row(
                span_id=sid,
                trace_id=tid,
                service_name=f"svc_{unique_id}",
                operation_name="crm.note.touch",
                start_time=t0,
                event_type="note.updated",
            )
        )
        row = await Span.get(sid)
        assert row is not None
        assert row.span_id == sid
        assert row.service_name == f"svc_{unique_id}"
        assert row.operation_name == "crm.note.touch"
        assert row.event_type == "note.updated"
        assert row.trace_id == tid
        await Span.insert_once(
            _span_row(
                span_id=sid,
                trace_id=tid,
                service_name=f"svc_{unique_id}",
                operation_name="crm.note.replaced",
                start_time=t0,
                event_type="note.updated",
            )
        )
        again = await Span.get(sid)
        assert again is not None
        assert again.operation_name == "crm.note.touch"
        with pytest.raises(ValueError, match="span.service_name is required to persist the span"):
            await Span.insert_once(
                _span_row(
                    span_id=f"{unique_id}_empty_service",
                    trace_id=tid,
                    service_name="",
                    operation_name="crm.note.touch",
                    start_time=t0,
                )
            )

    async def test_get_missing_returns_none(self, di, unique_id: str):
        row = await Span.get(f"{unique_id}_nope")
        assert row is None
        with pytest.raises(ValueError, match="Span span_id is required"):
            _ = await Span.get("")

    async def test_list_spans_for_service_filters_by_operation_name(
        self,
        di,
        unique_id: str,
    ):
        svc = f"sync_{unique_id}"
        base = datetime.now(timezone.utc)
        for i, op in enumerate(["sync.pull", "sync.push", "sync.pull"]):
            await Span.insert_once(
                _span_row(
                    span_id=f"{unique_id}_sn{i}",
                    trace_id=f"{unique_id}_tr{i}",
                    service_name=svc,
                    operation_name=op,
                    start_time=base + timedelta(microseconds=i),
                )
            )
        rows, _ = await Span.list_spans_for_service(
            service_name=svc,
            operation_name="sync.pull",
            limit=10,
        )
        assert len(rows) == 2
        assert {r.operation_name for r in rows} == {"sync.pull"}

    async def test_list_spans_for_service_filters_by_event_type(
        self,
        di,
        unique_id: str,
    ):
        svc = f"rag_{unique_id}"
        base = datetime.now(timezone.utc)
        for i, et in enumerate(["embed.started", "embed.done", "embed.started"]):
            await Span.insert_once(
                _span_row(
                    span_id=f"{unique_id}_ev{i}",
                    trace_id=f"{unique_id}_trx{i}",
                    service_name=svc,
                    operation_name="rag.embed",
                    start_time=base + timedelta(microseconds=i),
                    event_type=et,
                )
            )
        rows, _ = await Span.list_spans_for_service(
            service_name=svc,
            event_type="embed.started",
            limit=10,
        )
        assert len(rows) == 2
        assert {r.event_type for r in rows} == {"embed.started"}

    async def test_list_spans_for_service_respects_company_and_namespace(
        self,
        di,
        unique_id: str,
    ):
        svc = f"multi_{unique_id}"
        base = datetime.now(timezone.utc)
        await Span.insert_once(
            _span_row(
                span_id=f"{unique_id}_c1",
                trace_id=f"{unique_id}_t1",
                service_name=svc,
                operation_name="x",
                start_time=base,
                company_id="company_a",
                namespace="ns1",
            )
        )
        await Span.insert_once(
            _span_row(
                span_id=f"{unique_id}_c2",
                trace_id=f"{unique_id}_t2",
                service_name=svc,
                operation_name="x",
                start_time=base + timedelta(seconds=1),
                company_id="company_b",
                namespace="ns1",
            )
        )
        a_only, _ = await Span.list_spans_for_service(
            service_name=svc,
            company_id="company_a",
            limit=10,
        )
        assert len(a_only) == 1
        assert a_only[0].company_id == "company_a"

        ns_only, _ = await Span.list_spans_for_service(
            service_name=svc,
            company_id="company_b",
            namespace="ns1",
            limit=10,
        )
        assert len(ns_only) == 1
        assert ns_only[0].span_id == f"{unique_id}_c2"

    async def test_list_spans_for_service_cursor_no_duplicates_full_scan(
        self,
        di,
        unique_id: str,
    ):
        svc = f"page_{unique_id}"
        base = datetime.now(timezone.utc)
        n = 14
        for i in range(n):
            await Span.insert_once(
                _span_row(
                    span_id=f"{unique_id}_p{i:02d}",
                    trace_id=f"{unique_id}_pt{i}",
                    service_name=svc,
                    operation_name="batch.job",
                    start_time=base + timedelta(microseconds=i),
                )
            )
        page_size = 5
        cursor = None
        seen: set[str] = set()
        pages = 0
        while True:
            rows, next_c = await Span.list_spans_for_service(
                service_name=svc,
                limit=page_size,
                cursor=cursor,
            )
            pages += 1
            for r in rows:
                assert r.span_id not in seen
                seen.add(r.span_id)
            if next_c is None:
                break
            cursor = next_c
            assert pages <= 5
        assert len(seen) == n

    async def test_list_spans_for_service_invalid_cursor_raises(self, di, unique_id: str):
        with pytest.raises(ValueError, match="cursor"):
            await Span.list_spans_for_service(
                service_name=f"x_{unique_id}",
                limit=5,
                cursor="not-valid-base64!!!",
            )

    async def test_list_spans_for_service_limit_below_one_raises(self, di, unique_id: str):
        with pytest.raises(ValueError, match="limit"):
            await Span.list_spans_for_service(
                service_name=f"x_{unique_id}",
                limit=0,
            )

    async def test_services_isolated_by_service_name(
        self,
        di,
        unique_id: str,
    ):
        base = datetime.now(timezone.utc)
        await Span.insert_once(
            _span_row(
                span_id=f"{unique_id}_crm",
                trace_id=f"{unique_id}_tcrm",
                service_name=f"crm_{unique_id}",
                operation_name="entity.save",
                start_time=base,
            )
        )
        await Span.insert_once(
            _span_row(
                span_id=f"{unique_id}_sync",
                trace_id=f"{unique_id}_tsync",
                service_name=f"sync_{unique_id}",
                operation_name="channel.send",
                start_time=base,
            )
        )
        crm_rows, _ = await Span.list_spans_for_service(service_name=f"crm_{unique_id}", limit=20)
        sync_rows, _ = await Span.list_spans_for_service(service_name=f"sync_{unique_id}", limit=20)
        assert len(crm_rows) == 1
        assert len(sync_rows) == 1
        assert crm_rows[0].operation_name == "entity.save"
        assert sync_rows[0].operation_name == "channel.send"


@pytest.mark.asyncio
async def test_list_for_trace_orders_by_start_time(di: object, unique_id: str) -> None:
    _ = di
    trace_id = f"{unique_id}_trace"
    later = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    earlier = later - timedelta(seconds=5)
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_late",
            trace_id=trace_id,
            service_name=f"svc_{unique_id}",
            operation_name="late",
            start_time=later,
        )
    )
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_early",
            trace_id=trace_id,
            service_name=f"svc_{unique_id}",
            operation_name="early",
            start_time=earlier,
        )
    )
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_other",
            trace_id=f"{unique_id}_other_trace",
            service_name=f"svc_{unique_id}",
            operation_name="other",
            start_time=earlier,
        )
    )
    spans = await Span.list_for_trace(trace_id)
    assert [span.span_id for span in spans] == [f"{unique_id}_early", f"{unique_id}_late"]
    assert await Span.list_for_trace(f"{unique_id}_missing") == []


@pytest.mark.asyncio
async def test_list_by_task_id_orders_by_start_time(di: object, unique_id: str) -> None:
    _ = di
    task_id = f"{unique_id}_task"
    later = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    earlier = later - timedelta(seconds=5)
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_task_late",
            trace_id=f"{unique_id}_task_trace",
            service_name=f"svc_{unique_id}",
            operation_name="late",
            start_time=later,
        ).model_copy(update={"attributes": {"platform.task_id": task_id}})
    )
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_task_early",
            trace_id=f"{unique_id}_task_trace",
            service_name=f"svc_{unique_id}",
            operation_name="early",
            start_time=earlier,
        ).model_copy(update={"attributes": {"platform.task_id": task_id}})
    )
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_task_other",
            trace_id=f"{unique_id}_task_other_trace",
            service_name=f"svc_{unique_id}",
            operation_name="other",
            start_time=earlier,
        ).model_copy(update={"attributes": {"platform.task_id": f"{unique_id}_other_task"}})
    )
    spans = await Span.list_by_task_id(task_id)
    assert [span.span_id for span in spans] == [
        f"{unique_id}_task_early",
        f"{unique_id}_task_late",
    ]
    assert await Span.list_by_task_id(f"{unique_id}_missing_task") == []


@pytest.mark.asyncio
async def test_list_by_session_agent_orders_newest_first(di: object, unique_id: str) -> None:
    _ = di
    session_agent = f"{unique_id}_session"
    later = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    earlier = later - timedelta(seconds=5)
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_sess_early",
            trace_id=f"{unique_id}_sess_trace",
            service_name=f"svc_{unique_id}",
            operation_name="early",
            start_time=earlier,
        ).model_copy(update={"session_agent": session_agent})
    )
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_sess_late",
            trace_id=f"{unique_id}_sess_trace",
            service_name=f"svc_{unique_id}",
            operation_name="late",
            start_time=later,
        ).model_copy(update={"session_agent": session_agent})
    )
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_sess_other",
            trace_id=f"{unique_id}_sess_other_trace",
            service_name=f"svc_{unique_id}",
            operation_name="other",
            start_time=later,
        ).model_copy(update={"session_agent": f"{unique_id}_other_session"})
    )
    spans = await Span.list_by_session_agent(session_agent, limit=10)
    assert [span.span_id for span in spans] == [
        f"{unique_id}_sess_late",
        f"{unique_id}_sess_early",
    ]
    assert await Span.list_by_session_agent(f"{unique_id}_missing_session") == []


@pytest.mark.asyncio
async def test_list_by_user_id_orders_newest_first_and_keeps_bounds(
    di: object,
    unique_id: str,
) -> None:
    _ = di
    user_id = f"{unique_id}_user"
    middle = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    earlier = middle - timedelta(seconds=10)
    later = middle + timedelta(seconds=10)
    for span_id, start_time in (
        (f"{unique_id}_user_early", earlier),
        (f"{unique_id}_user_mid", middle),
        (f"{unique_id}_user_late", later),
    ):
        await Span.insert_once(
            _span_row(
                span_id=span_id,
                trace_id=f"{unique_id}_user_trace",
                service_name=f"svc_{unique_id}",
                operation_name=span_id,
                start_time=start_time,
            ).model_copy(update={"user_id": user_id})
        )
    await Span.insert_once(
        _span_row(
            span_id=f"{unique_id}_user_other",
            trace_id=f"{unique_id}_user_other_trace",
            service_name=f"svc_{unique_id}",
            operation_name="other",
            start_time=middle,
        ).model_copy(update={"user_id": f"{unique_id}_other_user"})
    )
    spans = await Span.list_by_user_id(user_id, from_time=earlier, to_time=middle, limit=10)
    assert [span.span_id for span in spans] == [
        f"{unique_id}_user_mid",
        f"{unique_id}_user_early",
    ]
    assert await Span.list_by_user_id(f"{unique_id}_missing_user") == []

