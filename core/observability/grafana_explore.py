"""
Deep-link вкладки Grafana Explore с предзаполненным LogQL.

Формат `left=` совместим с Grafana 9/10/11 Explore.
Селектор сервисов совпадает с whitelist в core.clients.loki_client (trace_id для платформы).
"""

from __future__ import annotations

import json
from urllib.parse import quote

# Должен оставаться согласован с _PLATFORM_TRACE_SELECTOR в core.clients.loki_client.
_PLATFORM_TRACE_SELECTOR = (
    'service=~"(agents|frontend|flows|flows_worker|crm|crm_worker|rag|rag_worker|'
    'sync|sync_worker|office|voice|scheduler|browser|idle_worker|provider_litserve|.*flows.*)"'
)


def sanitize_logql_value(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("sanitize_logql_value: value must be str")
    return value.replace('"', "").replace("\\", "").strip()


def build_platform_correlation_logql(*, trace_id: str | None, request_id: str) -> str:
    """
    Строит LogQL по whitelist: при непустом trace_id фильтрует по trace_id, иначе по request_id.
    """
    rid = sanitize_logql_value(request_id)
    if not rid:
        raise ValueError("build_platform_correlation_logql: request_id обязателен")

    tid = sanitize_logql_value(trace_id) if isinstance(trace_id, str) and trace_id.strip() else ""
    if tid:
        return f'{{{_PLATFORM_TRACE_SELECTOR}}} | json | trace_id="{tid}"'
    return f'{{{_PLATFORM_TRACE_SELECTOR}}} | json | request_id="{rid}"'


def build_grafana_explore_loki_url(
    *,
    grafana_public_url: str,
    datasource_uid: str,
    org_id: str,
    logql: str,
) -> str:
    if not isinstance(grafana_public_url, str) or not grafana_public_url.strip():
        raise ValueError("build_grafana_explore_loki_url: grafana_public_url обязателен")
    if not isinstance(datasource_uid, str) or not datasource_uid.strip():
        raise ValueError("build_grafana_explore_loki_url: datasource_uid обязателен")
    if not isinstance(org_id, str) or not org_id.strip():
        raise ValueError("build_grafana_explore_loki_url: org_id обязателен")
    if not isinstance(logql, str) or not logql.strip():
        raise ValueError("build_grafana_explore_loki_url: logql обязателен")

    base = grafana_public_url.strip().rstrip("/")
    uid = datasource_uid.strip()
    oid = org_id.strip()
    left: dict[str, object] = {
        "datasource": uid,
        "queries": [
            {
                "refId": "A",
                "expr": logql,
                "queryType": "range",
                "datasource": {"type": "loki", "uid": uid},
                "editorMode": "code",
            }
        ],
        "range": {"from": "now-24h", "to": "now"},
    }
    qs = quote(json.dumps(left, separators=(",", ":")), safe="")
    return f"{base}/explore?orgId={oid}&left={qs}"
