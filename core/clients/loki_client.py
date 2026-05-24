"""
LokiClient — HTTP-клиент для поиска логов в Grafana Loki.

Поддерживает только whitelist-шаблоны LogQL. По trace_id — сервисы платформы, где в лог
Попадает тот же OTel trace_id (frontend, agents HTTP flows, flows_worker, …); session/request/span/user —
селектор processes, где крутится runtime flows (agents + *flows* в имени контейнера в Loki). Произвольный LogQL от внешнего клиента не принимается.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

import httpx

from core.logging import get_logger
from core.models import StrictBaseModel
from core.types import JsonObject, JsonValue, parse_json_object, require_json_object

logger = get_logger(__name__)

_DEFAULT_QUERY_LOOKBACK = timedelta(days=7)

# Селектор сервисов: Loki label service выставляется Alloy из лейбла app=<name> Pod'а:
# Deployment flows → service=flows; воркеры flows_worker → service=flows-worker. Также сохраняется
# совместимость со старыми именами (agents, *flows*).
_FLOWS_SELECTOR = 'service=~"(agents|flows|.*flows.*)"'

# По trace_id — те же процессы; agents обязателен: иначе логи flows-сервиса на проде не попадают в выборку.
_PLATFORM_TRACE_SELECTOR = (
    'service=~"(agents|frontend|flows|flows_worker|crm|crm_worker|rag|rag_worker|'
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


class LokiLogEntry(StrictBaseModel):
    timestamp: str
    level: str
    message: str
    logger: str
    service: str
    trace_id: str
    span_id: str
    request_id: str
    user_id: str
    session_id: str
    session_agent: str
    raw: JsonObject


def _json_string(payload: Mapping[str, JsonValue], key: str, default: str = "") -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else default


def _stream_labels(raw_stream: JsonValue, field_name: str) -> dict[str, str]:
    stream_obj = require_json_object(raw_stream, field_name)
    labels: dict[str, str] = {}
    for key, value in stream_obj.items():
        if not isinstance(value, str):
            raise ValueError(f"{field_name}.{key} must be a string")
        labels[key] = value
    return labels


def _parse_entry(ts_ns: str, line: str, stream: Mapping[str, str]) -> LokiLogEntry:
    try:
        ts_iso = datetime.fromtimestamp(
            int(ts_ns) / 1_000_000_000, tz=timezone.utc
        ).isoformat()
    except (ValueError, TypeError):
        ts_iso = ts_ns

    parsed: JsonObject
    try:
        parsed = parse_json_object(line, "loki.log_line")
    except ValueError:
        parsed = {"message": line}

    message = _json_string(parsed, "message", _json_string(parsed, "msg"))
    return LokiLogEntry(
        timestamp=ts_iso,
        level=_json_string(parsed, "level", stream.get("level", "")),
        message=message,
        logger=_json_string(parsed, "logger"),
        service=_json_string(parsed, "service.name", stream.get("service", "")),
        trace_id=_json_string(parsed, "trace_id"),
        span_id=_json_string(parsed, "span_id"),
        request_id=_json_string(parsed, "request_id"),
        user_id=_json_string(parsed, "user_id"),
        session_id=_json_string(parsed, "session_id"),
        session_agent=_json_string(parsed, "session_agent"),
        raw=parsed,
    )


def _parse_loki_response(body: JsonObject) -> list[LokiLogEntry]:
    data = require_json_object(body.get("data"), "loki.data")
    raw_results = data.get("result")
    if not isinstance(raw_results, list):
        raise ValueError("loki.data.result must be an array")

    entries: list[LokiLogEntry] = []
    for result_index, raw_stream_result in enumerate(raw_results):
        stream_result = require_json_object(raw_stream_result, f"loki.data.result[{result_index}]")
        stream = _stream_labels(stream_result.get("stream", {}), f"loki.data.result[{result_index}].stream")
        raw_values = stream_result.get("values")
        if not isinstance(raw_values, list):
            raise ValueError(f"loki.data.result[{result_index}].values must be an array")
        for value_index, raw_value in enumerate(raw_values):
            if not isinstance(raw_value, list) or len(raw_value) < 2:
                raise ValueError(f"loki.data.result[{result_index}].values[{value_index}] must be [ts, line]")
            ts_ns = raw_value[0]
            line = raw_value[1]
            if not isinstance(ts_ns, str) or not isinstance(line, str):
                raise ValueError(
                    f"loki.data.result[{result_index}].values[{value_index}] must contain string ts and line"
                )
            entries.append(_parse_entry(ts_ns, line, stream))
    entries.sort(key=lambda entry: entry.timestamp)
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
        self._base_url: str = base_url.rstrip("/")
        self._timeout: float = timeout

    async def _query_range(
        self,
        logql: str,
        time_from: datetime | None,
        time_to: datetime | None,
        limit: int,
    ) -> list[LokiLogEntry]:
        end = time_to if time_to is not None else datetime.now(timezone.utc)
        start = time_from if time_from is not None else end - _DEFAULT_QUERY_LOOKBACK
        params: dict[str, str | int] = {
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
            body = parse_json_object(resp.text, "loki.query_range response")
            return _parse_loki_response(body)
        except ValueError as exc:
            snippet = (resp.text or "")[:300]
            raise LokiClientError(
                f"Loki query_range ответ не JSON/LogQL payload (HTTP {resp.status_code}): {snippet}"
            ) from exc

    async def query_by_trace_id(
        self,
        trace_id: str,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        limit: int = 200,
    ) -> list[LokiLogEntry]:
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
    ) -> list[LokiLogEntry]:
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
    ) -> list[LokiLogEntry]:
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
    ) -> list[LokiLogEntry]:
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
    ) -> list[LokiLogEntry]:
        """Возвращает записи логов с указанным user_id из flows/flows_worker."""
        if not user_id:
            raise ValueError("LokiClient.query_by_user_id: user_id обязателен")
        return await self._query_range(
            _build_user_id_query(user_id), time_from, time_to, limit
        )
