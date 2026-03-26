"""
Публичные маршруты PWA: manifest, service worker, offline-страница.
Файлы лежат в core/frontend/pwa/ и общие для всех сервисов.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse


def platform_pwa_assets_dir(project_root: Path) -> Path:
    return project_root / "core" / "frontend" / "pwa"


def register_platform_pwa_routes(app: FastAPI, project_root: Path) -> None:
    """
    Регистрирует GET /manifest.json, /sw.js, /offline.html.
    При отсутствии файлов — исключение при старте приложения.
    """
    pwa_dir = platform_pwa_assets_dir(project_root)
    manifest_path = pwa_dir / "manifest.json"
    sw_path = pwa_dir / "sw.js"
    offline_path = pwa_dir / "offline.html"

    if not manifest_path.is_file():
        raise FileNotFoundError(f"PWA manifest не найден: {manifest_path}")
    if not sw_path.is_file():
        raise FileNotFoundError(f"PWA sw.js не найден: {sw_path}")
    if not offline_path.is_file():
        raise FileNotFoundError(f"PWA offline.html не найден: {offline_path}")

    @app.get("/manifest.json")
    async def serve_manifest():
        return FileResponse(
            manifest_path,
            media_type="application/manifest+json",
        )

    @app.get("/sw.js")
    async def serve_service_worker():
        return FileResponse(
            sw_path,
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    @app.get("/offline.html")
    async def serve_offline():
        return FileResponse(offline_path)
