"""
Юнит-тесты для TempoClient: парсинг OTLP JSON и поведение при ошибках.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.clients.tempo_client import (
    TempoClient,
    TempoClientError,
    _bytes_to_hex,
    _normalize_status,
    _ns_to_iso,
    _parse_otlp_attributes,
    parse_otlp_trace,
)

# ---------------------------------------------------------------------------
# _bytes_to_hex
# ---------------------------------------------------------------------------

class TestBytesToHex:
    def test_empty_string(self):
        assert _bytes_to_hex("") == ""

    def test_none_returns_empty(self):
        assert _bytes_to_hex(None) == ""

    def test_already_hex_lowercase(self):
        assert _bytes_to_hex("abcdef0123456789") == "abcdef0123456789"

    def test_already_hex_uppercase(self):
        assert _bytes_to_hex("ABCDEF0123456789") == "abcdef0123456789"

    def test_bytes_input(self):
        assert _bytes_to_hex(b"\xab\xcd") == "abcd"

    def test_base64_input(self):
        # Строка только из hex-символов может быть и hex, и base64; OTLP отдаёт base64 с неоднозначными символами.
        import base64

        raw = b"\x00\x01\x02\xfb"
        encoded = base64.b64encode(raw).decode()
        assert "+" in encoded or "/" in encoded
        assert _bytes_to_hex(encoded) == raw.hex()


# ---------------------------------------------------------------------------
# _parse_otlp_attributes
# ---------------------------------------------------------------------------

class TestParseOtlpAttributes:
    def test_string_value(self):
        attrs = [{"key": "service.name", "value": {"stringValue": "flows"}}]
        assert _parse_otlp_attributes(attrs) == {"service.name": "flows"}

    def test_int_value(self):
        attrs = [{"key": "platform.llm.total_tokens", "value": {"intValue": "42"}}]
        assert _parse_otlp_attributes(attrs)["platform.llm.total_tokens"] == 42

    def test_bool_value(self):
        attrs = [{"key": "platform.is_resume", "value": {"boolValue": True}}]
        assert _parse_otlp_attributes(attrs)["platform.is_resume"] is True

    def test_empty_key_skipped(self):
        attrs = [{"key": "", "value": {"stringValue": "ignored"}}]
        assert _parse_otlp_attributes(attrs) == {}

    def test_none_value_skipped(self):
        attrs = [{"key": "x", "value": {}}]
        result = _parse_otlp_attributes(attrs)
        assert "x" not in result


# ---------------------------------------------------------------------------
# _ns_to_iso
# ---------------------------------------------------------------------------

class TestNsToIso:
    def test_converts_nanoseconds(self):
        iso = _ns_to_iso("1000000000000000000")
        assert iso is not None
        assert "2001" in iso

    def test_none_input(self):
        assert _ns_to_iso(None) is None

    def test_empty_input(self):
        assert _ns_to_iso("") is None

    def test_invalid_input(self):
        assert _ns_to_iso("not-a-number") is None


# ---------------------------------------------------------------------------
# _normalize_status
# ---------------------------------------------------------------------------

class TestNormalizeStatus:
    def test_no_status(self):
        assert _normalize_status(None) == "UNSET"

    def test_code_0(self):
        assert _normalize_status({"code": 0}) == "UNSET"

    def test_code_1(self):
        assert _normalize_status({"code": 1}) == "OK"

    def test_code_2(self):
        assert _normalize_status({"code": 2}) == "ERROR"

    def test_string_code(self):
        assert _normalize_status({"code": "STATUS_CODE_OK"}) == "STATUS_CODE_OK"


# ---------------------------------------------------------------------------
# parse_otlp_trace
# ---------------------------------------------------------------------------

_SAMPLE_OTLP_BODY = {
    "batches": [
        {
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": {"stringValue": "flows"}},
                ]
            },
            "scopeSpans": [
                {
                    "spans": [
                        {
                            "traceId": "abcdef1234567890abcdef1234567890",
                            "spanId": "1234567890abcdef",
                            "name": "flow.run",
                            "kind": 1,
                            "startTimeUnixNano": "1700000000000000000",
                            "endTimeUnixNano": "1700000001000000000",
                            "attributes": [
                                {"key": "platform.flow_id", "value": {"stringValue": "my_flow"}},
                                {"key": "platform.session.agent", "value": {"stringValue": "my_flow:ctx1"}},
                            ],
                            "status": {"code": 1},
                        },
                        {
                            "traceId": "abcdef1234567890abcdef1234567890",
                            "spanId": "aabbccddeeff0011",
                            "parentSpanId": "1234567890abcdef",
                            "name": "node.run",
                            "kind": 1,
                            "startTimeUnixNano": "1700000000100000000",
                            "endTimeUnixNano": "1700000000900000000",
                            "attributes": [
                                {"key": "platform.node_id", "value": {"stringValue": "main"}},
                            ],
                            "status": {"code": 1},
                        },
                    ]
                }
            ],
        }
    ]
}


class TestParseOtlpTrace:
    def test_returns_list(self):
        spans = parse_otlp_trace(_SAMPLE_OTLP_BODY)
        assert isinstance(spans, list)
        assert len(spans) == 2

    def test_span_fields_present(self):
        spans = parse_otlp_trace(_SAMPLE_OTLP_BODY)
        root = next(s for s in spans if s["parent_span_id"] is None)
        assert root["span_id"] == "1234567890abcdef"
        assert root["operation_name"] == "flow.run"
        assert root["service_name"] == "flows"
        assert root["flow_id"] == "my_flow"
        assert root["session_agent"] == "my_flow:ctx1"
        assert root["status"] == "OK"
        assert root["duration_ms"] == 1000

    def test_parent_span_id_set(self):
        spans = parse_otlp_trace(_SAMPLE_OTLP_BODY)
        child = next(s for s in spans if s["parent_span_id"] is not None)
        assert child["parent_span_id"] == "1234567890abcdef"
        assert child["node_id"] == "main"

    def test_empty_body(self):
        assert parse_otlp_trace({}) == []

    def test_empty_batches(self):
        assert parse_otlp_trace({"batches": []}) == []


# ---------------------------------------------------------------------------
# TempoClient (с мок httpx)
# ---------------------------------------------------------------------------

class TestTempoClientGetTrace:
    @pytest.mark.asyncio
    async def test_get_trace_returns_spans(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _SAMPLE_OTLP_BODY

        with patch("core.clients.tempo_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            client = TempoClient(base_url="http://tempo:3200")
            spans = await client.get_trace("abcdef1234567890abcdef1234567890")

        assert len(spans) == 2
        assert spans[0]["operation_name"] == "flow.run"

    @pytest.mark.asyncio
    async def test_get_trace_404_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("core.clients.tempo_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            client = TempoClient(base_url="http://tempo:3200")
            spans = await client.get_trace("nonexistent")

        assert spans == []

    @pytest.mark.asyncio
    async def test_get_trace_503_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "service unavailable"

        with patch("core.clients.tempo_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            client = TempoClient(base_url="http://tempo:3200")
            with pytest.raises(TempoClientError):
                await client.get_trace("some_trace_id")

    @pytest.mark.asyncio
    async def test_get_trace_empty_id_raises(self):
        client = TempoClient(base_url="http://tempo:3200")
        with pytest.raises(ValueError, match="trace_id обязателен"):
            await client.get_trace("")

    def test_constructor_empty_url_raises(self):
        with pytest.raises(ValueError, match="base_url обязателен"):
            TempoClient(base_url="")


class TestTempoClientSearch:
    @pytest.mark.asyncio
    async def test_search_returns_trace_ids(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "traces": [
                {"traceID": "abc123"},
                {"traceID": "def456"},
            ]
        }

        with patch("core.clients.tempo_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client_cls.return_value.__aexit__.return_value = AsyncMock(return_value=False)
            mock_client.get.return_value = mock_resp

            client = TempoClient(base_url="http://tempo:3200")
            ids = await client.search_trace_ids_by_attribute(
                "platform.session.agent", "flow1:ctx1"
            )

        assert ids == ["abc123", "def456"]

    @pytest.mark.asyncio
    async def test_search_empty_args_raises(self):
        client = TempoClient(base_url="http://tempo:3200")
        with pytest.raises(ValueError):
            await client.search_trace_ids_by_attribute("", "value")
