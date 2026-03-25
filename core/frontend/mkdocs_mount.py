"""Монтирование собранного MkDocs (`site/` в корне репозитория) на `/documentation/`."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


def mount_mkdocs_documentation(
    app: FastAPI,
    repo_root: Path,
    *,
    gateway_prefix: str | None = None,
) -> None:
    """
    Регистрирует GET /documentation -> 307 на /documentation/ и mount StaticFiles на /documentation/.
    Если gateway_prefix задан (например \"frontend\" для ingress), дублирует на /{gateway_prefix}/documentation/.
    Если каталога site/ нет — ничего не монтирует (лог предупреждения).
    """
    site = repo_root / "site"
    if not site.is_dir():
        logger.warning(
            "Каталог site/ не найден (make doc или uv run mkdocs build), URL /documentation недоступен"
        )
        return

    @app.get("/documentation", include_in_schema=False)
    async def redirect_documentation_trailing_slash() -> RedirectResponse:
        return RedirectResponse(url="/documentation/", status_code=307)

    app.mount(
        "/documentation/",
        StaticFiles(directory=str(site), html=True),
        name="mkdocs-documentation",
    )
    logger.info("Документация MkDocs: GET /documentation/ -> %s", site)

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
            StaticFiles(directory=str(site), html=True),
            name=f"mkdocs-documentation-{prefix}-prefix",
        )
        logger.info("Документация MkDocs: GET %s/ -> %s", gw_base, site)
