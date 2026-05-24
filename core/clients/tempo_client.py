"""
TempoClient — HTTP-клиент для чтения трейсов из Grafana Tempo.

Преобразует OTLP JSON ответы Tempo в формат, совместимый с
platform-trace-viewer и build_span_tree (как _serialize_span репозитория).
"""

import base64
from datetime import datetime, timezone

import httpx

from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)

_STATUS_CODE_MAP: dict[int, str] = {0: "UNSET", 1: "OK", 2: "ERROR"}


def _bytes_to_hex(val: str | bytes | None) -> str:
    """Приводит base64-строку или bytes к lowercase hex-строке."""
    if not val:
        return ""
    if isinstance(val, bytes):
        return val.hex()
    val = val.strip()
    if not val:
        return ""
    # Уже hex (16/32/64 символа)
    if all(c in "0123456789abcdefABCDEF" for c in val):
        return val.lower()
    # Base64 (OTLP JSON формат)
    try:
        padded = val + "=" * (-len(val) % 4)
        return base64.b64decode(padded).hex()
    except Exception:
        return val.lower()


def _parse_otlp_attribute_value(value: JsonObject) -> JsonValue:
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        raw = value["intValue"]
        if isinstance(raw, str | int | float):
            return int(raw)
        return None
    if "doubleValue" in value:
        raw = value["doubleValue"]
        if isinstance(raw, str | int | float):
            return float(raw)
        return None
    if "boolValue" in value:
        raw = value["boolValue"]
        return raw if isinstance(raw, bool) else None
    if "arrayValue" in value:
        raw_array = value["arrayValue"]
        if not isinstance(raw_array, dict):
            return []
        array_value = require_json_object(raw_array, "Tempo attribute arrayValue")
        raw_values = array_value.get("values", [])
        if not isinstance(raw_values, list):
            return []
        return [
            _parse_otlp_attribute_value(require_json_object(v, "Tempo attribute array item"))
            for v in raw_values
            if isinstance(v, dict)
        ]
    return None


def _parse_otlp_attributes(attrs: list[JsonValue]) -> JsonObject:
    result: JsonObject = {}
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        attr_obj = require_json_object(attr, "Tempo attribute")
        key = attr_obj.get("key", "")
        if not isinstance(key, str) or not key:
            continue
        raw_val = attr_obj.get("value")
        if not isinstance(raw_val, dict):
            continue
        val = _parse_otlp_attribute_value(require_json_object(raw_val, "Tempo attribute value"))
        if val is not None:
            result[key] = val
    return result


def _ns_to_iso(ns_str: JsonValue) -> str | None:
    if not ns_str:
        return None
    if not isinstance(ns_str, str | int | float) or isinstance(ns_str, bool):
        return None
    try:
        ns = int(ns_str)
        secs = ns / 1_000_000_000
        return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _normalize_status(status: JsonObject | None) -> str:
    if not status:
        return "UNSET"
    code = status.get("code", 0)
    if isinstance(code, str):
        return code.upper()
    if not isinstance(code, int | float) or isinstance(code, bool):
        return "UNSET"
    return _STATUS_CODE_MAP.get(int(code), "UNSET")


def parse_otlp_trace(body: JsonObject) -> list[JsonObject]:
    """
    Парсит тело ответа Tempo GET /api/traces/{traceID} (OTLP JSON) в список
    span-словарей, совместимых с build_span_tree и platform-trace-viewer.
    """
    spans: list[JsonObject] = []
    raw_batches = body.get("batches", [])
    if not isinstance(raw_batches, list):
        raise ValueError("Tempo trace response batches must be an array")
    for raw_batch in raw_batches:
        if not isinstance(raw_batch, dict):
            continue
        batch = require_json_object(raw_batch, "Tempo batch")
        raw_resource = batch.get("resource", {})
        resource = require_json_object(raw_resource, "Tempo resource") if isinstance(raw_resource, dict) else {}
        raw_resource_attrs = resource.get("attributes", [])
        resource_attrs = _parse_otlp_attributes(raw_resource_attrs if isinstance(raw_resource_attrs, list) else [])
        service_name = resource_attrs.get("service.name", "")
        raw_scope_spans = batch.get("scopeSpans", [])
        if not isinstance(raw_scope_spans, list):
            continue
        for raw_scope_spans_item in raw_scope_spans:
            if not isinstance(raw_scope_spans_item, dict):
                continue
            scope_spans = require_json_object(raw_scope_spans_item, "Tempo scopeSpans item")
            raw_spans = scope_spans.get("spans", [])
            if not isinstance(raw_spans, list):
                continue
            for raw_span in raw_spans:
                if not isinstance(raw_span, dict):
                    continue
                span = require_json_object(raw_span, "Tempo span")
                raw_trace_id = span.get("traceId")
                raw_span_id = span.get("spanId")
                trace_id = _bytes_to_hex(raw_trace_id if isinstance(raw_trace_id, str) else "")
                span_id = _bytes_to_hex(raw_span_id if isinstance(raw_span_id, str) else "")
                raw_parent = span.get("parentSpanId", "")
                parent_span_id: str | None = (
                    _bytes_to_hex(raw_parent) if isinstance(raw_parent, str) and raw_parent else None
                )

                start_ns = span.get("startTimeUnixNano")
                end_ns = span.get("endTimeUnixNano")

                duration_ms: int | None = None
                if (
                    isinstance(start_ns, str | int | float)
                    and not isinstance(start_ns, bool)
                    and isinstance(end_ns, str | int | float)
                    and not isinstance(end_ns, bool)
                ):
                    try:
                        duration_ms = max(0, int((int(end_ns) - int(start_ns)) / 1_000_000))
                    except (ValueError, TypeError):
                        pass

                raw_attrs = span.get("attributes", [])
                attrs = _parse_otlp_attributes(raw_attrs if isinstance(raw_attrs, list) else [])
                raw_status = span.get("status")
                status_obj = require_json_object(raw_status, "Tempo span status") if isinstance(raw_status, dict) else None
                status = _normalize_status(status_obj)
                status_message = status_obj.get("message", "") if status_obj else ""

                spans.append({
                    "span_id": span_id,
                    "trace_id": trace_id,
                    "parent_span_id": parent_span_id,
                    "operation_name": span.get("name", ""),
                    "kind": span.get("kind", 0),
                    "start_time": _ns_to_iso(start_ns),
                    "end_time": _ns_to_iso(end_ns),
                    "duration_ms": duration_ms,
                    "status": status,
                    "status_message": status_message,
                    "service_name": service_name,
                    "company_id": attrs.get("platform.tenant.company_id"),
                    "namespace": attrs.get("platform.tenant.namespace"),
                    "user_id": attrs.get("platform.user.id"),
                    "user_name": attrs.get("platform.user.name"),
                    "session_agent": attrs.get("platform.session.agent"),
                    "session_auth": attrs.get("platform.session.auth"),
                    "channel": attrs.get("platform.channel"),
                    "event_type": attrs.get("platform.event_type"),
                    "resource_type": attrs.get("platform.resource.type"),
                    "resource_id": attrs.get("platform.resource.id"),
                    "flow_id": attrs.get("platform.flow_id"),
                    "task_id": attrs.get("platform.task_id"),
                    "context_id": attrs.get("platform.context_id"),
                    "branch_id": attrs.get("platform.branch_id"),
                    "node_id": attrs.get("platform.node_id"),
                    "agent_name": attrs.get("platform.agent.name"),
                    "is_resume": attrs.get("platform.is_resume"),
                    "attributes": attrs,
                    "events": [],
                })
    return spans


class TempoClientError(Exception):
    """Ошибка при обращении к Grafana Tempo HTTP API."""


class TempoClient:
    """
    HTTP-клиент для Grafana Tempo.

    Методы:
    - get_trace(trace_id) → список spans (OTLP → нормализованный dict).
    - search_trace_ids_by_attribute(attr_name, attr_value, limit) → list[trace_id].
    """

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        if not base_url:
            raise ValueError("TempoClient: base_url обязателен")
        self._base_url: str = base_url.rstrip("/")
        self._timeout: float = timeout

    async def get_trace(self, trace_id: str) -> list[JsonObject]:
        """
        Возвращает нормализованный список spans для trace_id из Tempo.
        Если трейс не найден — возвращает пустой список.
        """
        if not trace_id:
            raise ValueError("TempoClient.get_trace: trace_id обязателен")
        url = f"{self._base_url}/api/traces/{trace_id}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers={"Accept": "application/json"})
        except httpx.RequestError as exc:
            raise TempoClientError(
                f"Tempo GET /api/traces/{trace_id} request error: {type(exc).__name__}"
            ) from exc
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise TempoClientError(
                f"Tempo GET /api/traces/{trace_id} вернул {resp.status_code}: {resp.text[:300]}"
            )
        return parse_otlp_trace(parse_json_object(resp.content, "Tempo trace response"))

    async def search_trace_ids_by_attribute(
        self,
        attr_name: str,
        attr_value: str,
        limit: int = 20,
    ) -> list[str]:
        """
        Возвращает список trace_id из Tempo через search API по атрибуту span.

        Использует Tempo tags search: ?tags=<attr_name>=<attr_value>.
        """
        if not attr_name or not attr_value:
            raise ValueError(
                "TempoClient.search_trace_ids_by_attribute: attr_name и attr_value обязательны"
            )
        url = f"{self._base_url}/api/search"
        params = {"tags": f"{attr_name}={attr_value}", "limit": limit}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
        except httpx.RequestError as exc:
            raise TempoClientError(
                f"Tempo GET /api/search request error: {type(exc).__name__}"
            ) from exc
        if resp.status_code != 200:
            raise TempoClientError(
                f"Tempo GET /api/search вернул {resp.status_code}: {resp.text[:300]}"
            )
        body = parse_json_object(resp.content, "Tempo search response")
        raw_traces = body.get("traces", [])
        if not isinstance(raw_traces, list):
            raise TempoClientError("Tempo search response traces must be an array")
        return [
            trace_id
            for t in raw_traces
            if isinstance(t, dict)
            for trace_id in [require_json_object(t, "Tempo trace search item").get("traceID")]
            if isinstance(trace_id, str) and trace_id
        ]
