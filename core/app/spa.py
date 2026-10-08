"""Lit SPA сервиса: статика core UI Kit, статика сервиса и catch-all на `index.html`.

Одна функция на все сервисы: `apps/<svc>/main.py` не держит своих `app.mount` и
`serve_<svc>_ui`. Вызывается после регистрации собственных маршрутов сервиса —
catch-all `/{segment}/{path}` обязан идти последним в таблице маршрутов.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.config.loader import get_project_root
from core.logging import get_logger

logger = get_logger(__name__)

CORE_FRONTEND_MOUNT_PATH = "/static/core"
_DEFAULT_EXCLUDED_PREFIXES: tuple[str, ...] = ("api/", "ui/static/", "ws", "assets/")


def resolve_ui_static_dir(ui_dir: Path) -> Path:
    """Директория, которую отдаёт mount статики сервиса.

    `apps/<svc>/ui-dist/` (esbuild-бандл `npm run build:ui`) приоритетнее
    `apps/<svc>/ui/`: после TS-миграции браузер получает только собранный
    бандл и скопированные ассеты; исходники `.ts` в прод не попадают.
    Без сборки (чистый dev-clone) mount остаётся на `ui/`.
    """
    dist_dir = ui_dir.parent / "ui-dist"
    if (dist_dir / "index.js").is_file():
        return dist_dir
    return ui_dir


def mount_service_spa(
    app: FastAPI,
    *,
    public_segment: str,
    ui_dir: Path,
    excluded_prefixes: Sequence[str] = _DEFAULT_EXCLUDED_PREFIXES,
    extra_static_mounts: Sequence[tuple[str, Path, str]] = (),
) -> None:
    """Монтирует `/static/core`, `/{segment}/ui/static` и catch-all `/{segment}/{path}` → index.html.

    `excluded_prefixes` — под-пути, которые SPA не обслуживает (API, статика, WS):
    для них catch-all отвечает 404, а не index.html.
    """
    ui_static_dir = resolve_ui_static_dir(ui_dir)
    index_file = ui_static_dir / "index.html"
    if not index_file.is_file():
        raise FileNotFoundError(f"SPA index.html not found: {index_file}")

    core_frontend_path = get_project_root() / "core" / "frontend" / "static"
    if not core_frontend_path.is_dir():
        raise FileNotFoundError(f"core/frontend/static not found: {core_frontend_path}")
    app.mount(
        CORE_FRONTEND_MOUNT_PATH,
        StaticFiles(directory=str(core_frontend_path)),
        name="core_frontend",
    )
    app.mount(
        f"/{public_segment}/ui/static",
        StaticFiles(directory=str(ui_static_dir), html=True),
        name=f"{public_segment}_ui",
    )
    for mount_path, directory, name in extra_static_mounts:
        if not directory.is_dir():
            raise FileNotFoundError(f"static mount {name}: catalog not found: {directory}")
        app.mount(mount_path, StaticFiles(directory=str(directory)), name=name)

    excluded = tuple(excluded_prefixes)

    @app.get(f"/{public_segment}", include_in_schema=False)
    @app.get(f"/{public_segment}/", include_in_schema=False)
    @app.get(f"/{public_segment}/{{path:path}}", include_in_schema=False)
    async def serve_service_spa(path: str = "") -> FileResponse:
        if path.startswith(excluded):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index_file)

    _ = serve_service_spa
    logger.info(
        "spa.mounted",
        public_segment=public_segment,
        ui_dir=str(ui_dir),
        extra_mounts=len(extra_static_mounts),
    )
