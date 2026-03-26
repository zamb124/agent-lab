"""
Тесты публичных маршрутов PWA (core/app/pwa_routes.py).

Интеграция с create_service_app(include_platform_pwa=True) при глобальном TESTING=true
в conftest не дублируется здесь: фабрика по умолчанию отключает PWA в тестовом окружении.
Полная проверка в браузере (регистрация SW, offline) — зона E2E / ручного теста.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.app.pwa_routes import register_platform_pwa_routes


@pytest.fixture
def pwa_client() -> TestClient:
    project_root = Path(__file__).resolve().parent.parent.parent
    app = FastAPI()
    register_platform_pwa_routes(app, project_root)
    return TestClient(app)


def test_manifest_json(pwa_client: TestClient) -> None:
    response = pwa_client.get("/manifest.json")
    assert response.status_code == 200
    assert "application/manifest" in response.headers["content-type"]
    body = response.json()
    assert body["name"]
    assert body["short_name"] == "Humanitec"
    assert body.get("start_url") == "/"
    assert body.get("scope") == "/"
    assert isinstance(body.get("icons"), list)
    assert len(body["icons"]) >= 1


def test_sw_js(pwa_client: TestClient) -> None:
    response = pwa_client.get("/sw.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert response.headers.get("service-worker-allowed") == "/"
    assert b"humanitec-static-v2" in response.content


def test_offline_html(pwa_client: TestClient) -> None:
    response = pwa_client.get("/offline.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Нет подключения" in response.text


def test_register_platform_pwa_routes_raises_when_assets_missing(tmp_path: Path) -> None:
    """Без каталога core/frontend/pwa с тремя файлами — явная ошибка при регистрации."""
    app = FastAPI()
    with pytest.raises(FileNotFoundError, match="PWA manifest"):
        register_platform_pwa_routes(app, tmp_path)
