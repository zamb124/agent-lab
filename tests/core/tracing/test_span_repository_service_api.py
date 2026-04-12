"""
Тесты SpanRepository: единый API для любого сервиса (service_name + операция + тип + курсор).

Персистентность — реальная БД platform_tracing (см. testing.mdc).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


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
) -> dict:
    return {
        "span_id": span_id,
        "trace_id": trace_id,
        "parent_span_id": None,
        "operation_name": operation_name,
        "kind": "INTERNAL",
        "start_time": start_time,
        "end_time": start_time,
        "duration_ms": 0,
        "status": "OK",
        "service_name": service_name,
        "company_id": company_id,
        "namespace": namespace,
        "user_id": None,
        "user_name": None,
        "user_groups": None,
        "session_auth": None,
        "session_agent": None,
        "channel": None,
        "event_type": event_type,
        "resource_type": None,
        "resource_id": None,
        "attributes": {},
        "events": [],
    }


@pytest.mark.asyncio
class TestSpanRepositoryServiceQuery:
    async def test_get_span_by_id_returns_saved_operation(
        self,
        container,
        unique_id: str,
    ):
        repo = container.span_repository
        sid = f"{unique_id}_op1"
        tid = f"{unique_id}_tr1"
        t0 = datetime.now(timezone.utc)
        await repo.save_span(
            _span_row(
                span_id=sid,
                trace_id=tid,
                service_name=f"svc_{unique_id}",
                operation_name="crm.note.touch",
                start_time=t0,
                event_type="note.updated",
            )
        )
        row = await repo.get_span_by_id(sid)
        assert row is not None
        assert row["span_id"] == sid
        assert row["service_name"] == f"svc_{unique_id}"
        assert row["operation_name"] == "crm.note.touch"
        assert row["event_type"] == "note.updated"
        assert row["trace_id"] == tid

    async def test_get_span_by_id_missing_returns_none(self, container, unique_id: str):
        row = await container.span_repository.get_span_by_id(f"{unique_id}_nope")
        assert row is None

    async def test_list_spans_for_service_filters_by_operation_name(
        self,
        container,
        unique_id: str,
    ):
        repo = container.span_repository
        svc = f"sync_{unique_id}"
        base = datetime.now(timezone.utc)
        for i, op in enumerate(["sync.pull", "sync.push", "sync.pull"]):
            await repo.save_span(
                _span_row(
                    span_id=f"{unique_id}_sn{i}",
                    trace_id=f"{unique_id}_tr{i}",
                    service_name=svc,
                    operation_name=op,
                    start_time=base + timedelta(microseconds=i),
                )
            )
        rows, _ = await repo.list_spans_for_service(
            service_name=svc,
            operation_name="sync.pull",
            limit=10,
        )
        assert len(rows) == 2
        assert {r["operation_name"] for r in rows} == {"sync.pull"}

    async def test_list_spans_for_service_filters_by_event_type(
        self,
        container,
        unique_id: str,
    ):
        repo = container.span_repository
        svc = f"rag_{unique_id}"
        base = datetime.now(timezone.utc)
        for i, et in enumerate(["embed.started", "embed.done", "embed.started"]):
            await repo.save_span(
                _span_row(
                    span_id=f"{unique_id}_ev{i}",
                    trace_id=f"{unique_id}_trx{i}",
                    service_name=svc,
                    operation_name="rag.embed",
                    start_time=base + timedelta(microseconds=i),
                    event_type=et,
                )
            )
        rows, _ = await repo.list_spans_for_service(
            service_name=svc,
            event_type="embed.started",
            limit=10,
        )
        assert len(rows) == 2
        assert {r["event_type"] for r in rows} == {"embed.started"}

    async def test_list_spans_for_service_respects_company_and_namespace(
        self,
        container,
        unique_id: str,
    ):
        repo = container.span_repository
        svc = f"multi_{unique_id}"
        base = datetime.now(timezone.utc)
        await repo.save_span(
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
        await repo.save_span(
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
        a_only, _ = await repo.list_spans_for_service(
            service_name=svc,
            company_id="company_a",
            limit=10,
        )
        assert len(a_only) == 1
        assert a_only[0]["company_id"] == "company_a"

        ns_only, _ = await repo.list_spans_for_service(
            service_name=svc,
            company_id="company_b",
            namespace="ns1",
            limit=10,
        )
        assert len(ns_only) == 1
        assert ns_only[0]["span_id"] == f"{unique_id}_c2"

    async def test_list_spans_for_service_cursor_no_duplicates_full_scan(
        self,
        container,
        unique_id: str,
    ):
        repo = container.span_repository
        svc = f"page_{unique_id}"
        base = datetime.now(timezone.utc)
        n = 14
        for i in range(n):
            await repo.save_span(
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
            rows, next_c = await repo.list_spans_for_service(
                service_name=svc,
                limit=page_size,
                cursor=cursor,
            )
            pages += 1
            for r in rows:
                assert r["span_id"] not in seen
                seen.add(r["span_id"])
            if next_c is None:
                break
            cursor = next_c
            assert pages <= 5
        assert len(seen) == n

    async def test_list_spans_for_service_invalid_cursor_raises(self, container, unique_id: str):
        with pytest.raises(ValueError, match="cursor"):
            await container.span_repository.list_spans_for_service(
                service_name=f"x_{unique_id}",
                limit=5,
                cursor="not-valid-base64!!!",
            )

    async def test_list_spans_for_service_limit_below_one_raises(self, container, unique_id: str):
        with pytest.raises(ValueError, match="limit"):
            await container.span_repository.list_spans_for_service(
                service_name=f"x_{unique_id}",
                limit=0,
            )

    async def test_services_isolated_by_service_name(
        self,
        container,
        unique_id: str,
    ):
        repo = container.span_repository
        base = datetime.now(timezone.utc)
        await repo.save_span(
            _span_row(
                span_id=f"{unique_id}_crm",
                trace_id=f"{unique_id}_tcrm",
                service_name=f"crm_{unique_id}",
                operation_name="entity.save",
                start_time=base,
            )
        )
        await repo.save_span(
            _span_row(
                span_id=f"{unique_id}_sync",
                trace_id=f"{unique_id}_tsync",
                service_name=f"sync_{unique_id}",
                operation_name="channel.send",
                start_time=base,
            )
        )
        crm_rows, _ = await repo.list_spans_for_service(service_name=f"crm_{unique_id}", limit=20)
        sync_rows, _ = await repo.list_spans_for_service(service_name=f"sync_{unique_id}", limit=20)
        assert len(crm_rows) == 1
        assert len(sync_rows) == 1
        assert crm_rows[0]["operation_name"] == "entity.save"
        assert sync_rows[0]["operation_name"] == "channel.send"


