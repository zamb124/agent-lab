"""Монтирование статической документации Zensical (documentation-dist/ в корне репозитория) на /documentation/."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.logging import get_logger

logger = get_logger(__name__)
DOCUMENTATION_DIST = "documentation-dist"


def mount_documentation_static(
    app: FastAPI,
    repo_root: Path,
    *,
    gateway_prefix: str | None = None,
) -> None:
    """
    Регистрирует GET /documentation -> 307 на /documentation/ и mount StaticFiles на /documentation/.
    Если gateway_prefix задан (например \"frontend\" для ingress), дублирует на /{prefix}/documentation/.
    Если каталога documentation-dist/ ещё нет, route всё равно регистрируется: make doc пересоздаёт
    этот каталог уже после старта dev-сервера.
    """
    dist = repo_root / DOCUMENTATION_DIST
    if not dist.is_dir():
        logger.warning(
            (
                "Каталог %s/ не найден (make doc: zensical.ru.toml + zensical.en.toml), "
                "URL /documentation будет доступен после сборки документации"
            ),
            DOCUMENTATION_DIST,
        )

    async def redirect_documentation_trailing_slash() -> RedirectResponse:
        return RedirectResponse(url="/documentation/", status_code=307)

    app.add_api_route(
        "/documentation",
        endpoint=redirect_documentation_trailing_slash,
        methods=["GET"],
        include_in_schema=False,
    )
    app.mount(
        "/documentation/",
        StaticFiles(directory=str(dist), html=True, check_dir=False),
        name="documentation-static",
    )
    logger.info("Документация: GET /documentation/ -> %s", dist)

    if gateway_prefix:
        prefix = gateway_prefix.strip().strip("/")
        if not prefix:
            raise ValueError("gateway_prefix не может быть пустым")

        gw_base = f"/{prefix}/documentation"

        async def redirect_gateway_documentation_slash() -> RedirectResponse:
            return RedirectResponse(url=f"{gw_base}/", status_code=307)

        app.add_api_route(
            gw_base,
            endpoint=redirect_gateway_documentation_slash,
            methods=["GET"],
            include_in_schema=False,
        )
        app.mount(
            f"{gw_base}/",
            StaticFiles(directory=str(dist), html=True, check_dir=False),
            name=f"documentation-static-{prefix}-prefix",
        )
        logger.info("Документация: GET %s/ -> %s", gw_base, dist)
