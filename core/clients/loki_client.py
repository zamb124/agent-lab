"""
LokiClient — HTTP-клиент для поиска логов в Grafana Loki.

Поддерживает только whitelist-шаблоны LogQL (по trace_id и session_id).
Произвольный LogQL от внешнего клиента не принимается.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_QUERY_LOOKBACK = timedelta(days=7)

# События flows и flows_worker: label service на push/Alloy может быть flows, flows_worker
# или суффикс/префикс от имени контейнера — держим широкий, но связанный с «flows» матч.
_FLOWS_SELECTOR = 'service=~".*flows.*"'


def _build_trace_query(trace_id: str) -> str:
    safe = trace_id.replace('"', "").replace("\\", "")
    return f'{{{_FLOWS_SELECTOR}}} | json | trace_id="{safe}"'


def _build_session_query(session_id: str) -> str:
    safe = session_id.replace('"', "").replace("\\", "")
    return f'{{{_FLOWS_SELECTOR}}} | json | session_agent="{safe}"'


def _parse_entry(ts_ns: str, line: str, stream: dict[str, str]) -> dict[str, Any]:
    try:
        ts_iso = datetime.fromtimestamp(
            int(ts_ns) / 1_000_000_000, tz=timezone.utc
        ).isoformat()
    except (ValueError, TypeError):
        ts_iso = ts_ns

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        parsed = {"message": line}

    return {
        "timestamp": ts_iso,
        "level": parsed.get("level", stream.get("level", "")),
        "message": parsed.get("message", parsed.get("msg", "")),
        "logger": parsed.get("logger", ""),
        "service": parsed.get("service.name", stream.get("service", "")),
        "trace_id": parsed.get("trace_id", ""),
        "request_id": parsed.get("request_id", ""),
        "user_id": parsed.get("user_id", ""),
        "session_id": parsed.get("session_id", ""),
        "session_agent": parsed.get("session_agent", ""),
        "raw": parsed,
    }


def _parse_loki_response(body: dict) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for stream_result in body.get("data", {}).get("result", []):
        stream: dict[str, str] = stream_result.get("stream", {})
        for value in stream_result.get("values", []):
            if len(value) >= 2:
                entries.append(_parse_entry(value[0], value[1], stream))
    entries.sort(key=lambda e: e["timestamp"])
    return entries


class LokiClientError(Exception):
    """Ошибка при обращении к Loki query API."""


class LokiClient:
    """
    HTTP-клиент для Grafana Loki.

    Использует только whitelist-шаблоны LogQL: по trace_id и session_id.
    """

    def __init__(self, base_url: str, timeout: float = 15.0) -> None:
        if not base_url:
            raise ValueError("LokiClient: base_url обязателен")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def _query_range(
        self,
        logql: str,
        time_from: datetime | None,
        time_to: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        end = time_to if time_to is not None else datetime.now(timezone.utc)
        start = time_from if time_from is not None else end - _DEFAULT_QUERY_LOOKBACK
        params: dict[str, Any] = {
            "query": logql,
            "limit": limit,
            "direction": "forward",
            "start": str(int(start.timestamp() * 1_000_000_000)),
            "end": str(int(end.timestamp() * 1_000_000_000)),
        }
        url = f"{self._base_url}/loki/api/v1/query_range"
        resp: httpx.Response | None = None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, params=params)
        except httpx.RequestError as exc:
            raise LokiClientError(f"Loki недоступен (сеть или таймаут): {exc}") from exc

        if resp.status_code != 200:
            raise LokiClientError(
                f"Loki query_range вернул {resp.status_code}: {resp.text[:300]}"
            )
        try:
            body = resp.json()
        except (json.JSONDecodeError, TypeError) as exc:
            snippet = (resp.text or "")[:300]
            raise LokiClientError(
                f"Loki query_range ответ не JSON (HTTP {resp.status_code}): {snippet}"
            ) from exc
        return _parse_loki_response(body)

    async def query_by_trace_id(
        self,
        trace_id: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Возвращает записи логов с указанным trace_id из flows/flows_worker."""
        if not trace_id:
            raise ValueError("LokiClient.query_by_trace_id: trace_id обязателен")
        return await self._query_range(
            _build_trace_query(trace_id), time_from, time_to, limit
        )

    async def query_by_session_id(
        self,
        session_id: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Возвращает записи логов с указанным session_id из flows/flows_worker."""
        if not session_id:
            raise ValueError("LokiClient.query_by_session_id: session_id обязателен")
        return await self._query_range(
            _build_session_query(session_id), time_from, time_to, limit
        )
