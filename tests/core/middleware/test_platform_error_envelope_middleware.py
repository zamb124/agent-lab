"""PlatformHttpErrorEnvelopeMiddleware: корреляция в JSON ошибок."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from core.middleware.access_log import AccessLogMiddleware
from core.middleware.platform_error_envelope import PlatformHttpErrorEnvelopeMiddleware
from core.models.identity_models import Company


class _CompanyInjectMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, company_id: str | None) -> None:
        super().__init__(app)
        self._company_id = company_id

    async def dispatch(self, request, call_next):
        if self._company_id is None:
            return await call_next(request)
        request.state.company = Company(company_id=self._company_id, name=self._company_id)
        return await call_next(request)


def _build_test_app(monkeypatch, *, inject_company_id: str | None) -> FastAPI:
    from core.config.models import LoggingConfig

    app = FastAPI()

    monkeypatch.setattr(
        "core.middleware.platform_error_envelope.get_settings",
        lambda: SimpleNamespace(
            logging=LoggingConfig(
                grafana_public_url="https://grafana.test.local",
                grafana_loki_datasource_uid="loki_ds",
                grafana_org_id="1",
            )
        ),
    )

    @app.get("/raises")
    async def raises_route():
        raise HTTPException(status_code=400, detail="bad request")

    app.add_middleware(AccessLogMiddleware, service_name="middleware_test_svc")
    app.add_middleware(_CompanyInjectMiddleware, company_id=inject_company_id)
    app.add_middleware(PlatformHttpErrorEnvelopeMiddleware, service_name="middleware_test_svc")

    return app


def test_envelope_adds_correlation_without_observability_for_non_system(
    monkeypatch: pytest.MonkeyPatch,
):
    from fastapi.testclient import TestClient

    app = _build_test_app(monkeypatch, inject_company_id="demo")
    with TestClient(app) as client:
        r = client.get("/raises")
    assert r.status_code == 400
    payload = r.json()
    assert "request_id" in payload
    assert "trace_id" in payload
    assert payload["service"] == "middleware_test_svc"
    assert "detail" in payload
    assert "observability" not in payload


def test_envelope_adds_logs_explore_url_for_system_company(monkeypatch: pytest.MonkeyPatch):
    from fastapi.testclient import TestClient

    app = _build_test_app(monkeypatch, inject_company_id="system")
    with TestClient(app) as client:
        r = client.get("/raises")
    assert r.status_code == 400
    payload = r.json()
    assert payload["observability"]["logs_explore_url"].startswith(
        "https://grafana.test.local/explore"
    )
