"""Lit SPA сервиса: статика core UI Kit, статика сервиса и catch-all на `index.html`.

Одна функция на все сервисы: `apps/<svc>/main.py` не держит своих `app.mount` и
`serve_<svc>_ui`. Вызывается после регистрации собственных маршрутов сервиса —
catch-all `/{segment}/{path}` обязан идти последним в таблице маршрутов.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.config.loader import get_project_root
from core.logging import get_logger

logger = get_logger(__name__)

CORE_FRONTEND_MOUNT_PATH = "/static/core"
CORE_LIB_MOUNT_PATH = "/static/core/lib"
_DEFAULT_EXCLUDED_PREFIXES: tuple[str, ...] = ("api/", "ui/static/", "ws", "assets/")


def mount_core_frontend(app: FastAPI) -> None:
    """Монтирует `/static/core/lib` на собранный `core/frontend/embed-dist`, затем `/static/core` на `core/frontend/static`.

    Порядок тот же, что у granian (`scripts/dev/run.py`, Helm): под `/static/core/lib` браузер получает
    только результат `npm run build:ui` — embed-бандлы по стабильным URL для внешних сайтов и не-TS
    ассеты lib/ (css, AudioWorklet); `.ts`-исходники не отдаются. Без сборки приложение не стартует.
    """
    frontend_root = get_project_root() / "core" / "frontend"
    embed_dist = frontend_root / "embed-dist"
    if not embed_dist.is_dir():
        raise FileNotFoundError(f"embed bundles are not built: {embed_dist} (run make ui-build)")
    static_root = frontend_root / "static"
    if not static_root.is_dir():
        raise FileNotFoundError(f"core/frontend/static not found: {static_root}")
    app.mount(CORE_LIB_MOUNT_PATH, StaticFiles(directory=str(embed_dist)), name="core_frontend_lib")
    app.mount(CORE_FRONTEND_MOUNT_PATH, StaticFiles(directory=str(static_root)), name="core_frontend")


def resolve_ui_static_dir(ui_dir: Path) -> Path:
    """Директория, которую отдаёт mount статики сервиса: `apps/<svc>/ui-dist/` из `npm run build:ui`.

    Браузер получает только бандл и скопированные ассеты; `.ts`-исходники `ui/` не отдаются.
    Без сборки приложение не стартует.
    """
    dist_dir = ui_dir.parent / "ui-dist"
    if not (dist_dir / "index.js").is_file():
        raise FileNotFoundError(f"UI bundle is not built: {dist_dir} (run make ui-build)")
    return dist_dir


def mount_service_spa(
    app: FastAPI,
    *,
    public_segment: str,
    ui_dir: Path,
    excluded_prefixes: Sequence[str] = _DEFAULT_EXCLUDED_PREFIXES,
    extra_static_mounts: Sequence[tuple[str, Path, str]] = (),
    spa_pages: Mapping[str, str] = {},
) -> None:
    """Монтирует core-статику (`mount_core_frontend`), `/{segment}/ui/static` и catch-all `/{segment}/{path}` → index.html.

    `excluded_prefixes` — под-пути, которые SPA не обслуживает (API, статика, WS):
    для них catch-all отвечает 404, а не index.html.

    `spa_pages` — дополнительные SPA-приложения того же ui-dist: ключ — первый
    сегмент пути (`"tsd"` → `/{segment}/tsd`, `/{segment}/tsd/...`), значение —
    имя html-файла в `ui-dist` (`"tsd.html"`). Совпадение точное по сегменту:
    `/{segment}/tsdfoo` остаётся за catch-all основного SPA.
    """
    ui_static_dir = resolve_ui_static_dir(ui_dir)
    index_file = ui_static_dir / "index.html"
    if not index_file.is_file():
        raise FileNotFoundError(f"SPA index.html not found: {index_file}")
    pages: dict[str, Path] = {}
    for prefix, filename in spa_pages.items():
        page_file = ui_static_dir / filename
        if not page_file.is_file():
            raise FileNotFoundError(f"SPA page not found: {page_file}")
        pages[prefix] = page_file

    mount_core_frontend(app)
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
        page_file = pages.get(path.partition("/")[0])
        return FileResponse(page_file if page_file is not None else index_file)

    _ = serve_service_spa
    logger.info(
        "spa.mounted",
        public_segment=public_segment,
        ui_dir=str(ui_dir),
        extra_mounts=len(extra_static_mounts),
    )
