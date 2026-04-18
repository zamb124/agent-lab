"""
Frontend Service - FastAPI приложение для управления платформой
"""
import logging
import os
from pathlib import Path

from core.config.testing import is_testing
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, PlainTextResponse, Response
from apps.frontend.api.auth import router as auth_router
from apps.frontend.api.embed_configs import router as embed_configs_router
from apps.frontend.api.invites import router as invites_router
from apps.frontend.api.team import router as team_router
from apps.frontend.api.api_keys import router as api_keys_router
from apps.frontend.api.billing import router as billing_router
from apps.frontend.api.settings import router as settings_router
from apps.frontend.api.services import router as services_router
from apps.frontend.api.scheduler import router as scheduler_router
from apps.frontend.api.leads import leads_router, lead_requests_router
from apps.frontend.api.platform_tracing import router as platform_tracing_router
from apps.frontend.api.platform_billing import router as platform_billing_router
from apps.frontend.api.payments_webhook import router as payments_webhook_router
from apps.frontend.api.yoomoney_oauth import router as yoomoney_oauth_router
from apps.frontend.config import FrontendSettings, get_frontend_settings
from apps.frontend.container import get_frontend_container
from apps.frontend.dependencies import ContainerDep
from core.app.factory import create_service_app
from core.identity.demo_bootstrap import ensure_demo_company_and_user
from core.identity.system_bootstrap import ensure_system_admin_membership

logger = logging.getLogger(__name__)

_FRONTEND_DEV_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|"
    r"^https?://([a-z0-9-]+\.)*lvh\.me(:\d+)?$"
)


INDEXABLE_PUBLIC_PATHS: tuple[str, ...] = (
    "/",
    "/documentation/",
    "/products/agents",
    "/products/rag",
    "/products/crm",
    "/products/sync",
    "/products/documents",
)


def _get_platform_public_base_url() -> str:
    base_url = get_frontend_settings().server.platform_public_base_url
    if not base_url:
        raise ValueError("server.platform_public_base_url must be configured for SEO files")
    return base_url.rstrip("/")


def _build_sitemap_xml(base_url: str) -> str:
    def _priority_for_path(path: str) -> str:
        if path.startswith("/products/"):
            return "0.90"
        if path == "/":
            return "0.80"
        if path == "/documentation/":
            return "0.70"
        return "0.50"

    urls_xml = "\n".join(
        (
            "  <url>",
            f"    <loc>{base_url}{path}</loc>",
            "    <changefreq>weekly</changefreq>",
            f"    <priority>{_priority_for_path(path)}</priority>",
            "  </url>",
        )
        for path in INDEXABLE_PUBLIC_PATHS
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls_xml}\n"
        "</urlset>\n"
    )


def _build_llms_txt(base_url: str) -> str:
    return (
        "# Humanitec\n\n"
        "> Humanitec is a business automation platform with AI flows and LLM agents, RAG knowledge search, CRM graph, "
        "team collaboration tools, and scheduler automation.\n\n"
        "Use canonical HTTPS URLs only.\n"
        "Prioritize public product and documentation pages.\n"
        "Do not rely on private app routes, authenticated dashboards, or API endpoints as primary sources.\n\n"
        "## Key Pages\n"
        f"- Platform Overview: {base_url}/\n"
        f"- Product Agents: {base_url}/products/agents\n"
        f"- Product RAG: {base_url}/products/rag\n"
        f"- Product CRM: {base_url}/products/crm\n"
        f"- Product Sync: {base_url}/products/sync\n"
        f"- Product Documents: {base_url}/products/documents\n"
        f"- Product Documentation: {base_url}/documentation/\n\n"
        "## Optional\n"
        f"- Service health endpoint (technical): {base_url}/health\n"
    )

async def on_startup(app: FastAPI, container, settings: FrontendSettings) -> None:
    if is_testing():
        return
    await ensure_system_admin_membership(container)
    await ensure_demo_company_and_user(container)
    n = await container.billing_service.ensure_settlement_rules_materialized_for_all_companies()
    logger.info("Биллинг: правила settlement проверены/записаны для компаний: %s", n)

    from core.clients.payment import PaymentProviderFactory
    PaymentProviderFactory.initialize()
    await PaymentProviderFactory.seed_access_tokens(container.shared_storage)
    logger.info("Платежные провайдеры инициализированы")


# Создаем приложение через фабрику (автоматически подключает middleware, контейнер и т.д.)
_frontend_settings = get_frontend_settings()
_frontend_cors_regex = getattr(_frontend_settings, "cors_allow_origin_regex", None)
_frontend_cors_origins = list(getattr(_frontend_settings, "cors_allow_origins", []))
if _frontend_cors_regex is None and _frontend_settings.server.debug and not is_testing():
    _frontend_cors_regex = _FRONTEND_DEV_CORS_ORIGIN_REGEX

app = create_service_app(
    service_name="frontend",
    settings_class=FrontendSettings,
    get_container=get_frontend_container,
    on_startup=on_startup,
    routers=[],
    pages_routers=[
        auth_router,
        embed_configs_router,
        invites_router,
        team_router,
        api_keys_router,
        billing_router,
        settings_router,
        services_router,
        scheduler_router,
        leads_router,
        lead_requests_router,
        platform_tracing_router,
        platform_billing_router,
        payments_webhook_router,
        yoomoney_oauth_router,
    ],
    title="Platform Management",
    description="Управление платформой: авторизация, компании, биллинг",
    version="1.0.0",
    api_version=None,
    include_crud_routers=False,
    documentation_gateway_prefix="frontend",
    cors_origins=_frontend_cors_origins,
    cors_allow_origin_regex=_frontend_cors_regex,
)

# Монтирование core/frontend (общая библиотека) - СНАЧАЛА монтируем статику!
core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount(
        "/static/core",
        StaticFiles(directory=str(core_frontend_path)),
        name="core-frontend"
    )
    logger.info(f"✅ Core frontend библиотека: {core_frontend_path}")

# Монтирование apps/frontend/ui (само приложение)
ui_path = Path(__file__).parent / "ui"
if ui_path.exists():
    app.mount(
        "/static/frontend",
        StaticFiles(directory=str(ui_path)),
        name="frontend-ui"
    )
    logger.info(f"✅ Frontend UI: {ui_path}")

# Удаляем дефолтный root endpoint от фабрики - ПОСЛЕ монтирования статики
# (он возвращает {"service": "core", "version": "1.0.0", "status": "running"})
# Заменим его на SPA fallback ниже
for route in list(app.routes):
    if hasattr(route, 'path') and route.path == "/":
        app.routes.remove(route)


@app.get("/api/health")
@app.get("/health")
async def health(container: ContainerDep):
    _ = container
    return {"status": "ok", "service": "frontend"}


@app.get("/l/{code}")
async def resolve_short_link(container: ContainerDep, code: str):
    target = await container.short_link_service.resolve_absolute_redirect_url(code.strip())
    if target is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена или истекла")
    return RedirectResponse(url=target, status_code=303)


@app.get("/api/public/legal")
@app.get("/frontend/api/public/legal")
async def get_public_legal(container: ContainerDep) -> JSONResponse:
    """Публичные юридические реквизиты для страниц policy/terms."""
    _ = container
    legal = get_frontend_settings().legal.model_dump()
    return JSONResponse(content=legal)


@app.get("/robots.txt")
@app.get("/frontend/robots.txt")
async def get_robots_txt(container: ContainerDep) -> PlainTextResponse:
    _ = container
    base_url = _get_platform_public_base_url()
    robots_txt = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /frontend/api/\n"
        "Disallow: /auth/\n"
        "Disallow: /frontend/api/auth/\n"
        "Disallow: /ws/\n"
        "Disallow: /frontend/ws/\n"
        "Disallow: /crm/\n"
        "Disallow: /sync/\n"
        "Disallow: /rag/\n"
        "Disallow: /flows/\n"
        "Disallow: /office/\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )
    return PlainTextResponse(content=robots_txt)


@app.get("/sitemap.xml")
@app.get("/frontend/sitemap.xml")
async def get_sitemap_xml(container: ContainerDep) -> Response:
    _ = container
    base_url = _get_platform_public_base_url()
    sitemap_xml = _build_sitemap_xml(base_url=base_url)
    return Response(content=sitemap_xml, media_type="application/xml")


@app.get("/llms.txt")
@app.get("/frontend/llms.txt")
async def get_llms_txt(container: ContainerDep) -> PlainTextResponse:
    _ = container
    base_url = _get_platform_public_base_url()
    return PlainTextResponse(content=_build_llms_txt(base_url=base_url))


# SPA fallback (все неизвестные пути → index.html)
@app.get("/")
@app.get("/{full_path:path}")
async def serve_spa(container: ContainerDep, full_path: str = ""):
    _ = container
    # Исключаем API, статику, WebSocket и PWA файлы
    # full_path может начинаться с frontend/ из-за префикса сервиса
    excluded = (
        "api/", "static/", "ws/", "l/",
        "documentation/", "documentation",
        "frontend/api/", "frontend/static/", "frontend/ws/",
        "frontend/documentation/", "frontend/documentation",
        "manifest.json", "sw.js", "offline.html",
        "robots.txt", "sitemap.xml", "llms.txt",
        "frontend/robots.txt", "frontend/sitemap.xml", "frontend/llms.txt",
    )
    if full_path.startswith(excluded) or full_path in ("manifest.json", "sw.js", "offline.html"):
        raise HTTPException(status_code=404)
    
    index_path = ui_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return {"message": "Frontend UI not built yet"}


if __name__ == "__main__":
    import uvicorn
    from apps.frontend.config import get_frontend_settings
    
    settings = get_frontend_settings()
    uvicorn.run(
        "apps.frontend.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )

