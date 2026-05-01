"""
Единые поля корреляции и опциональной ссылки Explore в телах ошибок (HTTP JSON, WS payload).
"""

from __future__ import annotations

from typing import Any

from core.config.models import LoggingConfig
from core.observability.grafana_explore import (
    build_grafana_explore_loki_url,
    build_platform_correlation_logql,
)


def merge_platform_error_into_dict(
    body: dict[str, Any],
    *,
    trace_id: str,
    platform_request_id: str,
    service_name: str,
    logging_cfg: LoggingConfig,
    active_company_id: str | None,
) -> dict[str, Any]:
    """
    Добавляет или перезаписывает ключи платформы: request_id (кореляция выполнения), trace_id, service.

    Поле observability.logs_explore_url — только при active_company_id == 'system' и заданном
    grafana_public_url + grafana_loki_datasource_uid.
    """
    if not isinstance(body, dict):
        raise TypeError("merge_platform_error_into_dict: body must be dict")
    if not isinstance(trace_id, str) or not trace_id.strip():
        raise ValueError("merge_platform_error_into_dict: trace_id обязателен")
    if not isinstance(platform_request_id, str) or not platform_request_id.strip():
        raise ValueError("merge_platform_error_into_dict: platform_request_id обязателен")
    if not isinstance(service_name, str) or not service_name.strip():
        raise ValueError("merge_platform_error_into_dict: service_name обязателен")

    merged: dict[str, Any] = dict(body)
    merged["request_id"] = platform_request_id.strip()
    merged["trace_id"] = trace_id.strip()
    merged["service"] = service_name.strip()

    observability: dict[str, str] | None = None
    base = getattr(logging_cfg, "grafana_public_url", None)
    uid = getattr(logging_cfg, "grafana_loki_datasource_uid", None)
    org_id = getattr(logging_cfg, "grafana_org_id", None)
    if (
        active_company_id == "system"
        and isinstance(base, str)
        and base.strip()
        and isinstance(uid, str)
        and uid.strip()
        and isinstance(org_id, str)
        and org_id.strip()
    ):
        logql = build_platform_correlation_logql(
            trace_id=trace_id.strip(),
            request_id=platform_request_id.strip(),
        )
        explore = build_grafana_explore_loki_url(
            grafana_public_url=base.strip(),
            datasource_uid=uid.strip(),
            org_id=org_id.strip(),
            logql=logql,
        )
        observability = {"logs_explore_url": explore}

    if observability is not None:
        merged["observability"] = observability
    elif "observability" in merged:
        del merged["observability"]

    return merged


def try_merge_platform_error_into_dict(
    body: dict[str, Any],
    *,
    trace_id: str | None,
    platform_request_id: str | None,
    service_name: str,
    logging_cfg: LoggingConfig,
    active_company_id: str | None,
) -> dict[str, Any]:
    """Как merge_platform_error_into_dict, но без raise при отсутствии id — возвращает body без изменений."""
    if (
        not isinstance(trace_id, str)
        or not trace_id.strip()
        or not isinstance(platform_request_id, str)
        or not platform_request_id.strip()
    ):
        return body
    return merge_platform_error_into_dict(
        body,
        trace_id=trace_id.strip(),
        platform_request_id=platform_request_id.strip(),
        service_name=service_name,
        logging_cfg=logging_cfg,
        active_company_id=active_company_id,
    )
