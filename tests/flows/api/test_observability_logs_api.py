"""
Тесты для API логов flows: GET /flows/api/v1/observability/logs/by-trace/{trace_id}
и GET /flows/api/v1/observability/logs/by-session/{session_id}.

Loki-клиент мокается через DI контейнер.
"""

import pytest

_LOKI_CACHE_KEY = "_cached_loki_client"


def _swap_loki_client_cache(container, replacement):
    had_key = _LOKI_CACHE_KEY in container.__dict__
    previous = container.__dict__.get(_LOKI_CACHE_KEY)
    container.__dict__[_LOKI_CACHE_KEY] = replacement
    return had_key, previous


def _restore_loki_client_cache(container, had_key, previous):
    if had_key:
        container.__dict__[_LOKI_CACHE_KEY] = previous
    else:
        container.__dict__.pop(_LOKI_CACHE_KEY, None)


_SAMPLE_LOG_ENTRIES = [
    {
        "timestamp": "2023-11-14T12:00:00+00:00",
        "level": "info",
        "message": "flow started",
        "logger": "apps.flows.src.runtime",
        "service": "flows",
        "trace_id": "abc123",
        "request_id": "req-1",
        "user_id": "user_test",
        "session_id": "my_flow:ctx1",
        "raw": {"message": "flow started"},
    }
]


class MockLokiClient:
    def __init__(self, entries=None, raise_error=False):
        self._entries = entries or []
        self._raise_error = raise_error

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


@pytest.fixture
def loki_entries():
    return _SAMPLE_LOG_ENTRIES


class TestLogsByTraceApi:
    """GET /flows/api/v1/observability/logs/by-trace/{trace_id}"""

    @pytest.mark.asyncio
    async def test_returns_entries_when_loki_configured(
        self, client, app, auth_headers_system, loki_entries
    ):
        from apps.flows.src.container import get_container
        container = get_container()
        had_key, previous = _swap_loki_client_cache(container, MockLokiClient(entries=loki_entries))
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
            _restore_loki_client_cache(container, had_key, previous)

    @pytest.mark.asyncio
    async def test_returns_503_when_loki_not_configured(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        had_key, previous = _swap_loki_client_cache(container, None)
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-trace/abc123",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
        finally:
            _restore_loki_client_cache(container, had_key, previous)

    @pytest.mark.asyncio
    async def test_returns_503_when_loki_unavailable(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        had_key, previous = _swap_loki_client_cache(container, MockLokiClient(raise_error=True))
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-trace/abc123",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
            assert "Loki недоступен" in resp.json()["detail"]
        finally:
            _restore_loki_client_cache(container, had_key, previous)

    @pytest.mark.asyncio
    async def test_limit_exceeding_max_returns_422(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        had_key, previous = _swap_loki_client_cache(container, MockLokiClient())
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-trace/abc123?limit=9999",
                headers=auth_headers_system,
            )
            assert resp.status_code == 422
        finally:
            _restore_loki_client_cache(container, had_key, previous)


class TestLogsBySessionApi:
    """GET /flows/api/v1/observability/logs/by-session/{session_id}"""

    @pytest.mark.asyncio
    async def test_returns_entries_when_loki_configured(
        self, client, app, auth_headers_system, loki_entries
    ):
        from apps.flows.src.container import get_container
        container = get_container()
        had_key, previous = _swap_loki_client_cache(container, MockLokiClient(entries=loki_entries))
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
            _restore_loki_client_cache(container, had_key, previous)

    @pytest.mark.asyncio
    async def test_returns_503_when_loki_not_configured(self, client, app, auth_headers_system):
        from apps.flows.src.container import get_container
        container = get_container()
        had_key, previous = _swap_loki_client_cache(container, None)
        try:
            resp = await client.get(
                "/flows/api/v1/observability/logs/by-session/my_flow%3Actx1",
                headers=auth_headers_system,
            )
            assert resp.status_code == 503
        finally:
            _restore_loki_client_cache(container, had_key, previous)
