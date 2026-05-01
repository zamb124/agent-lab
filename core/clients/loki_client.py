"""
LokiClient — HTTP-клиент для поиска логов в Grafana Loki.

Поддерживает только whitelist-шаблоны LogQL. По trace_id — сервисы платформы, где в лог
попадает тот же OTel trace_id (frontend, flows, воркеры и т.д.); session/request/span/user —
селектор flows. Произвольный LogQL от внешнего клиента не принимается.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from core.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_QUERY_LOOKBACK = timedelta(days=7)

# Селектор «только flows» — для session_agent и полей, специфичных в основном для flows.
_FLOWS_SELECTOR = 'service=~".*flows.*"'

# По trace_id ищем во всех основных процессах платформы: тот же trace_id в OTel уходит в
# логи frontend, flows, воркеров и т.д.; ограничение только .*flows.* отрезает линии с тем же trace.
_PLATFORM_TRACE_SELECTOR = (
    'service=~"(frontend|flows|flows_worker|crm|crm_worker|rag|rag_worker|'
    'sync|sync_worker|office|voice|scheduler|browser|idle_worker|provider_litserve|.*flows.*)"'
)


def _build_trace_query(trace_id: str) -> str:
    safe = trace_id.replace('"', "").replace("\\", "")
    return f'{{{_PLATFORM_TRACE_SELECTOR}}} | json | trace_id="{safe}"'


def _build_session_query(session_id: str) -> str:
    safe = session_id.replace('"', "").replace("\\", "")
    return f'{{{_FLOWS_SELECTOR}}} | json | session_agent="{safe}"'


def _build_request_id_query(request_id: str) -> str:
    safe = request_id.replace('"', "").replace("\\", "")
    return f'{{{_FLOWS_SELECTOR}}} | json | request_id="{safe}"'


def _build_span_id_query(span_id: str) -> str:
    safe = span_id.replace('"', "").replace("\\", "")
    return f'{{{_FLOWS_SELECTOR}}} | json | span_id="{safe}"'


def _build_user_id_query(user_id: str) -> str:
    safe = user_id.replace('"', "").replace("\\", "")
    return f'{{{_FLOWS_SELECTOR}}} | json | user_id="{safe}"'


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
        "span_id": parsed.get("span_id", ""),
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

    Whitelist-шаблоны LogQL на сервере; по trace_id — расширенный набор service-лейблов.
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
        """Возвращает записи логов с указанным trace_id (платформенные сервисы, см. селектор)."""
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

    async def query_by_request_id(
        self,
        request_id: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Возвращает записи логов с указанным request_id из flows/flows_worker."""
        if not request_id:
            raise ValueError("LokiClient.query_by_request_id: request_id обязателен")
        return await self._query_range(
            _build_request_id_query(request_id), time_from, time_to, limit
        )

    async def query_by_span_id(
        self,
        span_id: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Возвращает записи логов с указанным span_id из flows/flows_worker."""
        if not span_id:
            raise ValueError("LokiClient.query_by_span_id: span_id обязателен")
        return await self._query_range(
            _build_span_id_query(span_id), time_from, time_to, limit
        )

    async def query_by_user_id(
        self,
        user_id: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Возвращает записи логов с указанным user_id из flows/flows_worker."""
        if not user_id:
            raise ValueError("LokiClient.query_by_user_id: user_id обязателен")
        return await self._query_range(
            _build_user_id_query(user_id), time_from, time_to, limit
        )
