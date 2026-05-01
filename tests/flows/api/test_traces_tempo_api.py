"""
Тесты для Traces API flows после перехода на Tempo.

TempoClient мокается через DI контейнер.
"""

import pytest

from core.clients.tempo_client import TempoClientError


_SAMPLE_SPANS = [
    {
        "span_id": "aaaa0001",
        "trace_id": "trace001",
        "parent_span_id": None,
        "operation_name": "flow.run",
        "kind": 1,
        "start_time": "2023-11-14T12:00:00+00:00",
        "end_time": "2023-11-14T12:00:01+00:00",
        "duration_ms": 1000,
        "status": "OK",
        "status_message": "",
        "service_name": "flows",
        "flow_id": "my_flow",
        "task_id": None,
        "context_id": "ctx1",
        "branch_id": None,
        "node_id": None,
        "agent_name": None,
        "session_agent": "my_flow:ctx1",
        "company_id": None,
        "attributes": {},
        "events": [],
    }
]


class MockTempoClient:
    def __init__(self, spans=None, search_ids=None, raise_error=False):
        self._spans = spans or []
        self._search_ids = search_ids or []
        self._raise_error = raise_error

    async def get_trace(self, trace_id):
        if self._raise_error:
            raise TempoClientError("Tempo недоступен")
        return self._spans

    async def search_trace_ids_by_attribute(self, attr_name, attr_value, limit=20):
        if self._raise_error:
            raise TempoClientError("Tempo недоступен")
        return self._search_ids


class TestTracesTempoApiByTrace:
    """GET /flows/api/v1/traces/trace/{trace_id}"""

    @pytest.mark.asyncio
    async def test_returns_spans_tree(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        original = container.__dict__.get("tempo_client", None)
        container.__dict__["tempo_client"] = MockTempoClient(spans=_SAMPLE_SPANS)
        try:
            resp = await client.get(
                "/flows/api/v1/traces/trace/trace001",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["trace_id"] == "trace001"
            assert body["spans_count"] == 1
            assert isinstance(body["spans"], list)
            assert len(body["spans"]) == 1
            assert body["spans"][0]["operation_name"] == "flow.run"
        finally:
            if original is None:
                container.__dict__.pop("tempo_client", None)
            else:
                container.__dict__["tempo_client"] = original

    @pytest.mark.asyncio
    async def test_returns_503_when_tempo_unavailable(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        original = container.__dict__.get("tempo_client", None)
        container.__dict__["tempo_client"] = MockTempoClient(raise_error=True)
        try:
            resp = await client.get(
                "/flows/api/v1/traces/trace/trace001",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
        finally:
            if original is None:
                container.__dict__.pop("tempo_client", None)
            else:
                container.__dict__["tempo_client"] = original

    @pytest.mark.asyncio
    async def test_returns_empty_spans_when_not_found(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        original = container.__dict__.get("tempo_client", None)
        container.__dict__["tempo_client"] = MockTempoClient(spans=[])
        try:
            resp = await client.get(
                "/flows/api/v1/traces/trace/nonexistent",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["spans_count"] == 0
            assert body["spans"] == []
        finally:
            if original is None:
                container.__dict__.pop("tempo_client", None)
            else:
                container.__dict__["tempo_client"] = original


class TestTracesTempoApiBySession:
    """GET /flows/api/v1/traces/session/{session_id}"""

    @pytest.mark.asyncio
    async def test_returns_spans_tree_via_search_then_get(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        original = container.__dict__.get("tempo_client", None)
        container.__dict__["tempo_client"] = MockTempoClient(
            spans=_SAMPLE_SPANS, search_ids=["trace001"]
        )
        try:
            resp = await client.get(
                "/flows/api/v1/traces/session/my_flow%3Actx1",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["session_id"] == "my_flow:ctx1"
            assert body["spans_count"] == 1
        finally:
            if original is None:
                container.__dict__.pop("tempo_client", None)
            else:
                container.__dict__["tempo_client"] = original

    @pytest.mark.asyncio
    async def test_returns_503_when_tempo_unavailable(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        original = container.__dict__.get("tempo_client", None)
        container.__dict__["tempo_client"] = MockTempoClient(raise_error=True)
        try:
            resp = await client.get(
                "/flows/api/v1/traces/session/my_flow%3Actx1",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
        finally:
            if original is None:
                container.__dict__.pop("tempo_client", None)
            else:
                container.__dict__["tempo_client"] = original


class TestTracesTempoApiByTask:
    """GET /flows/api/v1/traces/task/{task_id}"""

    @pytest.mark.asyncio
    async def test_returns_spans_tree(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        original = container.__dict__.get("tempo_client", None)
        container.__dict__["tempo_client"] = MockTempoClient(
            spans=_SAMPLE_SPANS, search_ids=["trace001"]
        )
        try:
            resp = await client.get(
                "/flows/api/v1/traces/task/task001",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["task_id"] == "task001"
            assert body["spans_count"] == 1
        finally:
            if original is None:
                container.__dict__.pop("tempo_client", None)
            else:
                container.__dict__["tempo_client"] = original
