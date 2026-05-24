"""
Единые поля корреляции и опциональной ссылки Explore в телах ошибок (HTTP JSON, WS payload).
"""

from __future__ import annotations

from core.config.models import LoggingConfig
from core.observability.grafana_explore import (
    build_grafana_explore_loki_url,
    build_platform_correlation_logql,
)
from core.types import JsonObject


def merge_platform_error_into_dict(
    body: JsonObject,
    *,
    trace_id: str,
    platform_request_id: str,
    service_name: str,
    logging_cfg: LoggingConfig,
    active_company_id: str | None,
) -> JsonObject:
    """
    Добавляет или перезаписывает ключи платформы: request_id (кореляция выполнения), trace_id, service.

    Поле observability.logs_explore_url — только при active_company_id == 'system' и заданном
    grafana_public_url + grafana_loki_datasource_uid.
    """
    if not trace_id.strip():
        raise ValueError("merge_platform_error_into_dict: trace_id обязателен")
    if not platform_request_id.strip():
        raise ValueError("merge_platform_error_into_dict: platform_request_id обязателен")
    if not service_name.strip():
        raise ValueError("merge_platform_error_into_dict: service_name обязателен")

    merged: JsonObject = dict(body)
    merged["request_id"] = platform_request_id.strip()
    merged["trace_id"] = trace_id.strip()
    merged["service"] = service_name.strip()

    observability: JsonObject | None = None
    base = logging_cfg.grafana_public_url
    uid = logging_cfg.grafana_loki_datasource_uid
    org_id = logging_cfg.grafana_org_id
    if (
        active_company_id == "system"
        and base is not None
        and base.strip()
        and uid is not None
        and uid.strip()
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
    body: JsonObject,
    *,
    trace_id: str | None,
    platform_request_id: str | None,
    service_name: str,
    logging_cfg: LoggingConfig,
    active_company_id: str | None,
) -> JsonObject:
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
