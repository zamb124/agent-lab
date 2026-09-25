"""
Тесты для API логов flows: by-trace, by-session, by-request, by-span, by-user.

Loki-клиент подменяется на границе DI.
"""

import dataclasses

import pytest

from core.clients.loki_client import LokiLogEntry
from core.di.state import reset_app_di, set_app_di


def _swap_loki_client_cache(app, di, replacement):
    previous = set_app_di(app, dataclasses.replace(di, loki_client=replacement))
    return previous


def _restore_loki_client_cache(app, previous):
    reset_app_di(app, previous)


_SAMPLE_LOG_ENTRIES = [
    LokiLogEntry(
        timestamp="2023-11-14T12:00:00+00:00",
        level="info",
        message="flow started",
        logger="apps.flows.src.runtime",
        service="flows",
        trace_id="abc123",
        span_id="span01",
        request_id="req-1",
        user_id="user_test",
        session_id="my_flow:ctx1",
        session_agent="my_flow:ctx1",
        raw={"message": "flow started"},
    )
]


class MockLokiClient:
    def __init__(self, entries=None, raise_error=False, *, configured: bool = True):
        self._entries = entries or []
        self._raise_error = raise_error
        self.is_configured = configured

    async def query_by_trace_id(self, trace_id, time_from=None, time_to=None, limit=200):
        if self._raise_error:
            from core.clients.loki_client import LokiClientError
            raise LokiClientError("Loki недоступен")
        return self._entries

    async def query_by_session_id(self, session_id, time_from=None, time_to=None, limit=200):
        if self._raise_error:
            from core.clients.loki_client import LokiClientError
            raise LokiClientError("Loki недоступен")
        return self._entries

    async def query_by_request_id(self, request_id, time_from=None, time_to=None, limit=200):
        if self._raise_error:
            from core.clients.loki_client import LokiClientError
            raise LokiClientError("Loki недоступен")
        return self._entries

    async def query_by_span_id(self, span_id, time_from=None, time_to=None, limit=200):
        if self._raise_error:
            from core.clients.loki_client import LokiClientError
            raise LokiClientError("Loki недоступен")
        return self._entries

    async def query_by_user_id(self, user_id, time_from=None, time_to=None, limit=200):
        if self._raise_error:
            from core.clients.loki_client import LokiClientError
            raise LokiClientError("Loki недоступен")
        return self._entries


@pytest.fixture
def loki_entries():
    return _SAMPLE_LOG_ENTRIES


class TestLogsByTraceApi:
    """GET /flows/api/v1/observability/logs/by-trace/{trace_id}"""

    @pytest.mark.asyncio
    async def test_returns_entries_when_loki_configured(
        self, client, app, auth_headers_system, loki_entries,
    di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(entries=loki_entries))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-trace/abc123",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["trace_id"] == "abc123"
            assert body["count"] == 1
            assert len(body["entries"]) == 1
            assert body["entries"][0]["message"] == "flow started"
        finally:
            _restore_loki_client_cache(app, previous)

    @pytest.mark.asyncio
    async def test_returns_503_when_loki_not_configured(self, client, app, auth_headers_system, di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(configured=False))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-trace/abc123",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
        finally:
            _restore_loki_client_cache(app, previous)

    @pytest.mark.asyncio
    async def test_returns_503_when_loki_unavailable(self, client, app, auth_headers_system, di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(raise_error=True))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-trace/abc123",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
            body = resp.json()
            assert body["error_code"] == "unavailable"
            assert "Loki is unavailable" in body["error_detail"] or "Loki недоступен" in body["error_detail"]
        finally:
            _restore_loki_client_cache(app, previous)

    @pytest.mark.asyncio
    async def test_limit_exceeding_max_returns_422(self, client, app, auth_headers_system, di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient())
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-trace/abc123?limit=9999",
                headers=auth_headers_system,
            )
            assert resp.status_code == 422
        finally:
            _restore_loki_client_cache(app, previous)


class TestLogsBySessionApi:
    """GET /flows/api/v1/observability/logs/by-session/{session_id}"""

    @pytest.mark.asyncio
    async def test_returns_entries_when_loki_configured(
        self, client, app, auth_headers_system, loki_entries,
    di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(entries=loki_entries))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-session/my_flow%3Actx1",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["session_id"] == "my_flow:ctx1"
            assert body["count"] == 1
        finally:
            _restore_loki_client_cache(app, previous)

    @pytest.mark.asyncio
    async def test_returns_503_when_loki_not_configured(self, client, app, auth_headers_system, di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(configured=False))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-session/my_flow%3Actx1",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
        finally:
            _restore_loki_client_cache(app, previous)


class TestLogsByRequestApi:
    """GET /flows/api/v1/observability/logs/by-request/{request_id}"""

    @pytest.mark.asyncio
    async def test_returns_entries(self, client, app, auth_headers_system, loki_entries, di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(entries=loki_entries))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-request/req-1",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["request_id"] == "req-1"
            assert body["count"] == 1
        finally:
            _restore_loki_client_cache(app, previous)


class TestLogsBySpanApi:
    """GET /flows/api/v1/observability/logs/by-span/{span_id}"""

    @pytest.mark.asyncio
    async def test_returns_entries(self, client, app, auth_headers_system, loki_entries, di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(entries=loki_entries))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-span/span01",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["span_id"] == "span01"
            assert body["count"] == 1
        finally:
            _restore_loki_client_cache(app, previous)


class TestLogsByUserApi:
    """GET /flows/api/v1/observability/logs/by-user/{user_id}"""

    @pytest.mark.asyncio
    async def test_returns_entries(self, client, app, auth_headers_system, loki_entries, di):
        previous = _swap_loki_client_cache(app, di, MockLokiClient(entries=loki_entries))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-user/user_test",
                headers=auth_headers_system,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["user_id"] == "user_test"
            assert body["count"] == 1
        finally:
            _restore_loki_client_cache(app, previous)
