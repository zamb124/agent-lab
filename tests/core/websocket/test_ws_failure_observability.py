"""WS failure payload enrichment (корреляция смерджена тем же кодом что HTTP)."""

from types import SimpleNamespace

import pytest

from core.config.models import LoggingConfig
from core.websocket.router import _merge_ws_failure_payload


@pytest.fixture(autouse=True)
def _fake_grafana(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "core.websocket.router.get_settings",
        lambda: SimpleNamespace(
            logging=LoggingConfig(
                grafana_public_url="https://grafana.ws.test",
                grafana_loki_datasource_uid="loki_ws",
                grafana_org_id="1",
            )
        ),
    )


def test_ws_merge_demo_no_observability() -> None:
    out = _merge_ws_failure_payload(
        {"error_code": "e1", "error_detail": "d"},
        trace_id="tw",
        platform_request_id="rw",
        service_name="sync",
        active_company_id="demo",
    )
    assert out["request_id"] == "rw"
    assert out["trace_id"] == "tw"
    assert out["service"] == "sync"
    assert "observability" not in out


def test_ws_merge_system_has_logs_url() -> None:
    out = _merge_ws_failure_payload(
        {"error_code": "e1", "error_detail": "d"},
        trace_id="tw",
        platform_request_id="rw",
        service_name="sync",
        active_company_id="system",
    )
    assert out["observability"]["logs_explore_url"].startswith("https://grafana.ws.test/explore")
