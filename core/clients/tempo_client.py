"""
TempoClient — HTTP-клиент для чтения трейсов из Grafana Tempo.

Преобразует OTLP JSON ответы Tempo в формат, совместимый с
platform-trace-viewer и build_span_tree (как _serialize_span репозитория).
"""

import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from core.logging import get_logger

logger = get_logger(__name__)

_STATUS_CODE_MAP: dict[int, str] = {0: "UNSET", 1: "OK", 2: "ERROR"}


def _bytes_to_hex(val: Any) -> str:
    """Приводит base64-строку или bytes к lowercase hex-строке."""
    if not val:
        return ""
    if isinstance(val, bytes):
        return val.hex()
    if not isinstance(val, str):
        return ""
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


def _parse_otlp_attribute_value(value: dict) -> Any:
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "arrayValue" in value:
        return [
            _parse_otlp_attribute_value(v)
            for v in value["arrayValue"].get("values", [])
        ]
    return None


def _parse_otlp_attributes(attrs: list[dict]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for attr in attrs:
        key = attr.get("key", "")
        if not key:
            continue
        raw_val = attr.get("value")
        if not isinstance(raw_val, dict):
            continue
        val = _parse_otlp_attribute_value(raw_val)
        if val is not None:
            result[key] = val
    return result


def _ns_to_iso(ns_str: Any) -> str | None:
    if not ns_str:
        return None
    try:
        ns = int(ns_str)
        secs = ns / 1_000_000_000
        return datetime.fromtimestamp(secs, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _normalize_status(status: dict | None) -> str:
    if not status:
        return "UNSET"
    code = status.get("code", 0)
    if isinstance(code, str):
        return code.upper()
    return _STATUS_CODE_MAP.get(int(code), "UNSET")


def parse_otlp_trace(body: dict) -> list[dict[str, Any]]:
    """
    Парсит тело ответа Tempo GET /api/traces/{traceID} (OTLP JSON) в список
    span-словарей, совместимых с build_span_tree и platform-trace-viewer.
    """
    spans: list[dict[str, Any]] = []
    for batch in body.get("batches", []):
        resource_attrs = _parse_otlp_attributes(
            batch.get("resource", {}).get("attributes", [])
        )
        service_name = resource_attrs.get("service.name", "")
        for scope_spans in batch.get("scopeSpans", []):
            for span in scope_spans.get("spans", []):
                trace_id = _bytes_to_hex(span.get("traceId", ""))
                span_id = _bytes_to_hex(span.get("spanId", ""))
                raw_parent = span.get("parentSpanId", "")
                parent_span_id: str | None = _bytes_to_hex(raw_parent) if raw_parent else None

                start_ns = span.get("startTimeUnixNano")
                end_ns = span.get("endTimeUnixNano")

                duration_ms: int | None = None
                if start_ns and end_ns:
                    try:
                        duration_ms = max(0, int((int(end_ns) - int(start_ns)) / 1_000_000))
                    except (ValueError, TypeError):
                        pass

                attrs = _parse_otlp_attributes(span.get("attributes", []))
                status_obj = span.get("status") if isinstance(span.get("status"), dict) else None
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
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """
        Возвращает нормализованный список spans для trace_id из Tempo.
        Если трейс не найден — возвращает пустой список.
        """
        if not trace_id:
            raise ValueError("TempoClient.get_trace: trace_id обязателен")
        url = f"{self._base_url}/api/traces/{trace_id}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise TempoClientError(
                f"Tempo GET /api/traces/{trace_id} вернул {resp.status_code}: {resp.text[:300]}"
            )
        return parse_otlp_trace(resp.json())

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
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            raise TempoClientError(
                f"Tempo GET /api/search вернул {resp.status_code}: {resp.text[:300]}"
            )
        body = resp.json()
        return [
            t["traceID"]
            for t in body.get("traces", [])
            if isinstance(t.get("traceID"), str) and t["traceID"]
        ]
