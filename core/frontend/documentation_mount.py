"""Монтирование статической документации Zensical (documentation-dist/ в корне репозитория) на /documentation/."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

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
    Если каталога documentation-dist/ нет — ничего не монтирует (предупреждение в лог).
    """
    dist = repo_root / DOCUMENTATION_DIST
    if not dist.is_dir():
        logger.warning(
            "Каталог %s/ не найден (make doc: zensical.ru.toml + zensical.en.toml), URL /documentation недоступен",
            DOCUMENTATION_DIST,
        )
        return

    @app.get("/documentation", include_in_schema=False)
    async def redirect_documentation_trailing_slash() -> RedirectResponse:
        return RedirectResponse(url="/documentation/", status_code=307)

    app.mount(
        "/documentation/",
        StaticFiles(directory=str(dist), html=True),
        name="documentation-static",
    )
    logger.info("Документация: GET /documentation/ -> %s", dist)

    if gateway_prefix:
        prefix = gateway_prefix.strip().strip("/")
        if not prefix:
            raise ValueError("gateway_prefix не может быть пустым")

        gw_base = f"/{prefix}/documentation"

        @app.get(gw_base, include_in_schema=False)
        async def redirect_gateway_documentation_slash() -> RedirectResponse:
            return RedirectResponse(url=f"{gw_base}/", status_code=307)

        app.mount(
            f"{gw_base}/",
            StaticFiles(directory=str(dist), html=True),
            name=f"documentation-static-{prefix}-prefix",
        )
        logger.info("Документация: GET %s/ -> %s", gw_base, dist)
