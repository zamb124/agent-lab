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
    assert "no-store" in response.headers.get("cache-control", "").lower()
    assert b"humanitec-static-" in response.content
    assert b"humanitec-dynamic-" in response.content
    assert b"CACHE_SCHEMA_VERSION" in response.content


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


def test_assetlinks_json_when_file_present(tmp_path: Path) -> None:
    """При наличии core/frontend/pwa/assetlinks.json — отдача /.well-known/assetlinks.json."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    src_pwa = repo_root / "core" / "frontend" / "pwa"
    dst_pwa = tmp_path / "core" / "frontend" / "pwa"
    dst_pwa.mkdir(parents=True)
    for name in ("manifest.json", "sw.js", "offline.html"):
        (dst_pwa / name).write_bytes((src_pwa / name).read_bytes())
    (dst_pwa / "assetlinks.json").write_text(
        '[{"relation":["delegate_permission/common.handle_all_urls"],'
        '"target":{"namespace":"android_app","package_name":"ru.test.twa",'
        '"sha256_cert_fingerprints":["AA:BB:CC"]}}]',
        encoding="utf-8",
    )
    app = FastAPI()
    register_platform_pwa_routes(app, tmp_path)
    client = TestClient(app)
    response = client.get("/.well-known/assetlinks.json")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    data = response.json()
    assert data[0]["target"]["package_name"] == "ru.test.twa"


def test_apple_app_site_association_when_file_present(tmp_path: Path) -> None:
    """При наличии apple-app-site-association — отдача /.well-known/apple-app-site-association."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    src_pwa = repo_root / "core" / "frontend" / "pwa"
    dst_pwa = tmp_path / "core" / "frontend" / "pwa"
    dst_pwa.mkdir(parents=True)
    for name in ("manifest.json", "sw.js", "offline.html"):
        (dst_pwa / name).write_bytes((src_pwa / name).read_bytes())
    (dst_pwa / "apple-app-site-association").write_bytes(
        (src_pwa / "apple-app-site-association").read_bytes()
    )
    app = FastAPI()
    register_platform_pwa_routes(app, tmp_path)
    client = TestClient(app)
    response = client.get("/.well-known/apple-app-site-association")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    data = response.json()
    assert "applinks" in data
    assert data["applinks"]["details"][0]["appIDs"][0].endswith("ru.humanitec.app")
