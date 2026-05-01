"""Тело ошибок платформы: merge полей корреляции и deep-link Grafana."""

from core.config.models import LoggingConfig
from core.observability.error_payload import merge_platform_error_into_dict
from core.observability.grafana_explore import (
    build_grafana_explore_loki_url,
    build_platform_correlation_logql,
)


def test_build_platform_correlation_logql_prioritizes_trace_id() -> None:
    ql = build_platform_correlation_logql(trace_id="abc_trace", request_id="req_1")
    assert 'trace_id="abc_trace"' in ql


def test_build_platform_correlation_logql_falls_back_to_request_id() -> None:
    ql = build_platform_correlation_logql(trace_id=None, request_id="rid_x")
    assert 'request_id="rid_x"' in ql


def test_build_grafana_explore_loki_url_has_explore_and_left() -> None:
    url = build_grafana_explore_loki_url(
        grafana_public_url="https://grafana.example",
        datasource_uid="ds1",
        org_id="1",
        logql='{service=~"agents"}',
    )
    assert url.startswith("https://grafana.example/explore?orgId=1&left=%7B")


def test_merge_adds_observability_for_system_only() -> None:
    logging_cfg = LoggingConfig(
        grafana_public_url="https://grafana.example",
        grafana_loki_datasource_uid="loki_uid",
        grafana_org_id="1",
    )
    out_demo = merge_platform_error_into_dict(
        {"detail": "x"},
        trace_id="t1",
        platform_request_id="r1",
        service_name="flows",
        logging_cfg=logging_cfg,
        active_company_id="demo",
    )
    assert out_demo["request_id"] == "r1"
    assert out_demo["trace_id"] == "t1"
    assert out_demo["service"] == "flows"
    assert "observability" not in out_demo

    out_system = merge_platform_error_into_dict(
        {"detail": "x"},
        trace_id="t1",
        platform_request_id="r1",
        service_name="flows",
        logging_cfg=logging_cfg,
        active_company_id="system",
    )
    obs = out_system["observability"]
    assert isinstance(obs, dict)
    assert "logs_explore_url" in obs
    assert obs["logs_explore_url"].startswith("https://grafana.example/explore")


def test_merge_strips_client_observability_for_non_system() -> None:
    logging_cfg = LoggingConfig()
    out = merge_platform_error_into_dict(
        {"detail": "x", "observability": {"logs_explore_url": "http://evil.example"}},
        trace_id="t1",
        platform_request_id="r1",
        service_name="flows",
        logging_cfg=logging_cfg,
        active_company_id="demo",
    )
    assert "observability" not in out
