"""
Юнит-тесты для LokiClient: парсинг ответов Loki и whitelist LogQL-шаблоны.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.clients.loki_client import (
    LokiClient,
    LokiClientError,
    _build_request_id_query,
    _build_session_query,
    _build_span_id_query,
    _build_trace_query,
    _build_user_id_query,
    _parse_entry,
    _parse_loki_response,
)
from core.config.models import LoggingConfig

# ---------------------------------------------------------------------------
# Query builders
# ---------------------------------------------------------------------------

class TestQueryBuilders:
    def test_trace_query_contains_trace_id(self):
        q = _build_trace_query("abc123")
        assert 'trace_id="abc123"' in q
        assert "agents" in q
        assert "flows" in q
        assert "frontend" in q

    def test_session_query_includes_agents_and_flows_services(self):
        q = _build_session_query("flow1:ctx1")
        assert "| json |" in q
        assert 'session_agent="flow1:ctx1"' in q
        assert "agents" in q
        assert "flows" in q

    def test_trace_query_sanitizes_quotes(self):
        # Кавычки внутри trace_id должны быть удалены для безопасности
        q = _build_trace_query('abc"inject')
        assert '"inject' not in q

    def test_session_query_sanitizes_backslash(self):
        q = _build_session_query("flow\\ctx")
        assert "flowctx" in q
        assert "flow\\ctx" not in q

    def test_session_query_strips_quotes_in_session_id(self):
        q = _build_session_query('flow"inj:ctx')
        assert 'session_agent="flowinj:ctx"' in q

    def test_user_query_uses_json_user_id(self):
        q = _build_user_id_query("user_abc")
        assert '| json |' in q
        assert 'user_id="user_abc"' in q
        assert "flows" in q

    def test_request_id_query(self):
        q = _build_request_id_query("req-1")
        assert 'request_id="req-1"' in q
        assert "flows" in q

    def test_span_id_query(self):
        q = _build_span_id_query("span01")
        assert 'span_id="span01"' in q
        assert "flows" in q


# ---------------------------------------------------------------------------
# _parse_entry
# ---------------------------------------------------------------------------

class TestParseEntry:
    def test_parses_json_line(self):
        line = json.dumps({
            "level": "info",
            "message": "flow started",
            "trace_id": "abc123",
            "session_id": "flow1:ctx1",
            "service.name": "flows",
        })
        entry = _parse_entry("1700000000000000000", line, {})
        assert entry.level == "info"
        assert entry.message == "flow started"
        assert entry.trace_id == "abc123"
        assert entry.session_id == "flow1:ctx1"
        assert "2023" in entry.timestamp

    def test_fallback_for_non_json_line(self):
        entry = _parse_entry("1700000000000000000", "plain text log", {})
        assert entry.message == "plain text log"

    def test_level_from_stream_when_missing_in_json(self):
        line = json.dumps({"message": "test"})
        entry = _parse_entry("1700000000000000000", line, {"level": "warn"})
        assert entry.level == "warn"


# ---------------------------------------------------------------------------
# _parse_loki_response
# ---------------------------------------------------------------------------

_SAMPLE_LOKI_RESPONSE = {
    "data": {
        "resultType": "streams",
        "result": [
            {
                "stream": {"service": "flows", "level": "info"},
                "values": [
                    ["1700000001000000000", json.dumps({"message": "first", "level": "info", "trace_id": "t1"})],
                    ["1700000002000000000", json.dumps({"message": "second", "level": "debug", "trace_id": "t1"})],
                ],
            }
        ],
    }
}


class TestParseLokiResponse:
    def test_returns_sorted_entries(self):
        entries = _parse_loki_response(_SAMPLE_LOKI_RESPONSE)
        assert len(entries) == 2
        assert entries[0].message == "first"
        assert entries[1].message == "second"

    def test_empty_result(self):
        assert _parse_loki_response({"data": {"result": []}}) == []

    def test_empty_body(self):
        with pytest.raises(ValueError, match="loki.data"):
            _parse_loki_response({})


# ---------------------------------------------------------------------------
# LokiClient (с мок httpx)
# ---------------------------------------------------------------------------

class TestLokiClientQueryByTraceId:
    @pytest.mark.asyncio
    async def test_returns_entries(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _SAMPLE_LOKI_RESPONSE
        mock_resp.text = json.dumps(_SAMPLE_LOKI_RESPONSE)

        with patch("core.clients.loki_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            client = LokiClient(base_url="http://loki:3100")
            entries = await client.query_by_trace_id("t1")

        assert len(entries) == 2
        assert entries[0].message == "first"

    @pytest.mark.asyncio
    async def test_loki_error_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal error"

        with patch("core.clients.loki_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            client = LokiClient(base_url="http://loki:3100")
            with pytest.raises(LokiClientError, match="query_range вернул 500"):
                await client.query_by_trace_id("t1")

    @pytest.mark.asyncio
    async def test_request_error_raises(self):
        import httpx

        class FakeInner:
            async def get(self, *args, **kwargs):
                raise httpx.ConnectError("connection refused", request=MagicMock())

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = FakeInner()
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("core.clients.loki_client.httpx.AsyncClient", return_value=mock_cm):
            client = LokiClient(base_url="http://loki:3100")
            with pytest.raises(LokiClientError, match="сеть или таймаут"):
                await client.query_by_trace_id("t1")

    @pytest.mark.asyncio
    async def test_empty_trace_id_raises(self):
        client = LokiClient(base_url="http://loki:3100")
        with pytest.raises(ValueError, match="trace_id обязателен"):
            await client.query_by_trace_id("")

    def test_constructor_empty_url_raises(self):
        with pytest.raises(ValueError, match="base_url обязателен"):
            LokiClient(base_url="")


class TestLokiClientQueryBySessionId:
    @pytest.mark.asyncio
    async def test_returns_entries(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _SAMPLE_LOKI_RESPONSE
        mock_resp.text = json.dumps(_SAMPLE_LOKI_RESPONSE)

        with patch("core.clients.loki_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            client = LokiClient(base_url="http://loki:3100")
            entries = await client.query_by_session_id("flow1:ctx1")

        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_empty_session_id_raises(self):
        client = LokiClient(base_url="http://loki:3100")
        with pytest.raises(ValueError, match="session_id обязателен"):
            await client.query_by_session_id("")


class TestLokiClientQueryByRequestId:
    @pytest.mark.asyncio
    async def test_empty_request_id_raises(self):
        client = LokiClient(base_url="http://loki:3100")
        with pytest.raises(ValueError, match="request_id обязателен"):
            await client.query_by_request_id("")


class TestLokiClientQueryBySpanId:
    @pytest.mark.asyncio
    async def test_empty_span_id_raises(self):
        client = LokiClient(base_url="http://loki:3100")
        with pytest.raises(ValueError, match="span_id обязателен"):
            await client.query_by_span_id("")


class TestLokiClientQueryByUserId:
    @pytest.mark.asyncio
    async def test_empty_user_id_raises(self):
        client = LokiClient(base_url="http://loki:3100")
        with pytest.raises(ValueError, match="user_id обязателен"):
            await client.query_by_user_id("")


# ---------------------------------------------------------------------------
# LoggingConfig.resolve_loki_query_http_base
# ---------------------------------------------------------------------------


class TestLoggingConfigResolveLokiQueryHttpBase:
    def test_explicit_loki_query_url_strips_slash(self):
        cfg = LoggingConfig(loki_query_url="http://localhost:3100/")
        assert cfg.resolve_loki_query_http_base() == "http://localhost:3100"

    def test_derived_from_push_url(self):
        cfg = LoggingConfig(
            loki_url="http://localhost:3100/loki/api/v1/push",
            loki_query_url=None,
        )
        assert cfg.resolve_loki_query_http_base() == "http://localhost:3100"

    def test_explicit_query_overrides_push(self):
        cfg = LoggingConfig(
            loki_query_url="http://loki-query:9999",
            loki_url="http://localhost:3100/loki/api/v1/push",
        )
        assert cfg.resolve_loki_query_http_base() == "http://loki-query:9999"

    def test_none_when_no_urls(self):
        cfg = LoggingConfig()
        assert cfg.resolve_loki_query_http_base() is None

    def test_malformed_push_returns_none(self):
        cfg = LoggingConfig(loki_url="not-a-valid-url")
        assert cfg.resolve_loki_query_http_base() is None
