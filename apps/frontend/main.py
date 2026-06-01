""""
Сервис frontend — FastAPI-приложение для управления платформой
"""

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route

from apps.frontend.api.ai_providers import router as ai_providers_router
from apps.frontend.api.api_keys import router as api_keys_router
from apps.frontend.api.auth import router as auth_router
from apps.frontend.api.billing import router as billing_router
from apps.frontend.api.companies import router as companies_router
from apps.frontend.api.company_pronunciation_rules import (
    router as company_pronunciation_rules_router,
)
from apps.frontend.api.company_voice_providers import (
    router as company_voice_providers_router,
)
from apps.frontend.api.embed_configs import router as embed_configs_router
from apps.frontend.api.invites import router as invites_router
from apps.frontend.api.leads import lead_requests_router, leads_router
from apps.frontend.api.payments_webhook import router as payments_webhook_router
from apps.frontend.api.platform_billing import router as platform_billing_router
from apps.frontend.api.platform_llm_model_scores import (
    router as platform_llm_model_scores_router,
)
from apps.frontend.api.platform_pronunciation_rules import (
    router as platform_pronunciation_rules_router,
)
from apps.frontend.api.platform_tracing import router as platform_tracing_router
from apps.frontend.api.public_docs_assistant import router as public_docs_assistant_router
from apps.frontend.api.public_landing_agents import router as public_landing_agents_router
from apps.frontend.api.public_search import router as public_search_router
from apps.frontend.api.public_site import router as public_site_router
from apps.frontend.api.scheduler import router as scheduler_router
from apps.frontend.api.search_providers import router as search_providers_router
from apps.frontend.api.services import router as services_router
from apps.frontend.api.settings import router as settings_router
from apps.frontend.api.team import router as team_router
from apps.frontend.api.voice_providers_catalog import router as voice_providers_catalog_router
from apps.frontend.api.yoomoney_oauth import router as yoomoney_oauth_router
from apps.frontend.config import (
    FrontendSettings,
    get_frontend_public_base_url,
    get_frontend_settings,
)
from apps.frontend.container import FrontendContainer, get_frontend_container
from apps.frontend.dependencies import ContainerDep
from apps.frontend.services.docs_assistant_bootstrap import schedule_docs_assistant_bootstrap
from apps.frontend.services.flow_preview_guest_html import (
    build_flow_preview_guest_html,
    build_flow_preview_unavailable_html,
)
from core.app.factory import create_service_app
from core.app.health_payload import build_health_payload
from core.app_state import get_request_correlation_ids
from core.clients.payment import PaymentProviderFactory
from core.clients.voice_resolver import invalidate_platform_pronunciation_cache
from core.config import get_settings
from core.config.testing import is_testing
from core.identity.demo_bootstrap import ensure_demo_company_and_user
from core.identity.flow_preview_handoff import (
    consume_flow_preview_handoff,
    peek_flow_preview_handoff,
)
from core.identity.system_bootstrap import ensure_system_admin_membership
from core.logging import get_logger
from core.middleware.auth.company_resolver import build_service_base_url
from core.middleware.static_core_module_cors import StaticCoreModuleCorsMiddleware
from core.short_links.kinds import SHORT_LINK_KIND_FLOW_PREVIEW_EMBED
from core.short_links.payloads import FlowPreviewEmbedPayload

logger = get_logger(__name__)
_FRONTEND_DEV_CORS_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|"
    r"^https?://([a-z0-9-]+\.)*lvh\.me(:\d+)?$"
)

INDEXABLE_PUBLIC_PATHS: tuple[str, ...] = (
    "/",
    "/documentation/",
    "/support",
    "/products/agents",
    "/products/rag",
    "/products/crm",
    "/products/sync",
    "/products/documents",
    "/demo/digital-workers",
    "/blog",
    "/about",
    "/roadmap",
)

def _flow_preview_preferred_lang(request: Request) -> str:
    """ru | en по Accept-Language (первый упомянутый язык)."""
    header = (request.headers.get("accept-language") or "").lower()
    for part in header.split(","):
        token = part.split(";")[0].strip()
        if not token:
            continue
        if token.startswith("en"):
            return "en"
        if token.startswith("ru"):
            return "ru"
    return "ru"


def _flow_preview_unavailable_response(request: Request) -> Response:
    lang = _flow_preview_preferred_lang(request)
    correlation = get_request_correlation_ids(request)
    request_id = correlation.request_id if correlation is not None else None
    body = build_flow_preview_unavailable_html(lang=lang, request_id=request_id)
    return Response(status_code=404, content=body, media_type="text/html; charset=utf-8")


def _short_link_redirect_location(target: str) -> str:
    """Относительный path+query: браузер остаётся на том же host:port, что и GET /l/{code}.

    В development DevInterServiceProxyMiddleware пересылает /sync/* на server.sync_service_url.
    Абсолютный URL из platform_public_base_url не используется в Location, чтобы не уводить
    на другой домен и не зависеть от совпадения host с запросом.
    """
    p = urlparse(target)
    loc = p.path
    if p.query:
        loc = f"{loc}?{p.query}"
    return loc

def _build_sitemap_xml(base_url: str) -> str:
    lastmod = datetime.now(UTC).strftime("%Y-%m-%d")
    og_image_loc = f"{base_url}/static/frontend/assets/images/main_img.png"
    paths_with_preview_image: frozenset[str] = frozenset(
        (
            "/",
            "/products/agents",
            "/products/rag",
            "/products/crm",
            "/products/sync",
            "/products/documents",
            "/demo/digital-workers",
        )
    )

    def _priority_for_path(path: str) -> str:
        if path.startswith("/products/"):
            return "0.90"
        if path == "/":
            return "0.80"
        if path == "/documentation/":
            return "0.70"
        if path == "/support":
            return "0.65"
        if path in ("/blog", "/about", "/roadmap"):
            return "0.55"
        return "0.50"

    def _url_block(path: str) -> str:
        lines = [
            "  <url>",
            f"    <loc>{base_url}{path}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            "    <changefreq>weekly</changefreq>",
            f"    <priority>{_priority_for_path(path)}</priority>",
        ]
        if path in paths_with_preview_image:
            lines.extend(
                (
                    "    <image:image>",
                    f"      <image:loc>{og_image_loc}</image:loc>",
                    "    </image:image>",
                )
            )
        lines.append("  </url>")
        return "\n".join(lines)

    urls_xml = "\n".join(_url_block(path) for path in INDEXABLE_PUBLIC_PATHS)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'
        f"{urls_xml}\n"
        "</urlset>\n"
    )

def _build_llms_txt(base_url: str) -> str:
    return (
        "# Humanitec\n\n"
        "> Humanitec is a business automation platform with AI flows and LLM agents, RAG knowledge search, NetWorkle graph, "
        "team collaboration tools, and scheduler automation.\n\n"
        "Use canonical HTTPS URLs only.\n"
        "Prioritize public product and documentation pages.\n"
        "Do not rely on private app routes, authenticated dashboards, or API endpoints as primary sources.\n\n"
        "## Key Pages\n"
        f"- Platform Overview: {base_url}/\n"
        f"- Product Agents: {base_url}/products/agents\n"
        f"- Product RAG: {base_url}/products/rag\n"
        f"- Product NetWorkle: {base_url}/products/crm\n"
        f"- Product Sync: {base_url}/products/sync\n"
        f"- Product Documents: {base_url}/products/documents\n"
        f"- Product Documentation: {base_url}/documentation/\n"
        f"- Support: {base_url}/support\n"
        f"- Blog: {base_url}/blog\n"
        f"- About: {base_url}/about\n"
        f"- Roadmap: {base_url}/roadmap\n\n"
        "## Optional\n"
        f"- Service health endpoint (technical): {base_url}/health\n"
    )

async def _seed_platform_pronunciation_rules(container: FrontendContainer) -> None:
    """Засевает платформенные правила произношения при первом старте (идемпотентно)."""
    if not get_settings().voice.tts.pronunciation_seed_enabled:
        return
    repo = container.platform_pronunciation_rule_repository
    existing = await repo.list_all()
    existing_patterns = {(r.kind, r.pattern, r.language) for r in existing}

    seed_rules = [
        ("alias", "Хуманитик", "хуманитэк", "ru"),
        ("alias", "Humanitec", "хуманитэк", "ru"),
        ("alias", "humanitec", "хуманитэк", "ru"),
        ("stress", "Хуманитик", "хум+анитэк", "ru"),
        ("stress", "humanitec", "хум+анитэк", "ru"),
    ]
    for kind, pattern, replacement, lang in seed_rules:
        if (kind, pattern, lang) not in existing_patterns:
            _ = await repo.create(
                kind=kind,
                pattern=pattern,
                replacement=replacement,
                language=lang,
                word_boundary=True,
                case_sensitive=False,
                note="Платформенное правило (seed)",
            )
    invalidate_platform_pronunciation_cache()
    logger.info("frontend.pronunciation_seed_applied")


async def _seed_llm_model_scores(container: FrontendContainer) -> None:
    """Засевает shared скоринг LLM-моделей из конфигурации."""
    scoring = get_settings().llm.model_scoring
    if not scoring.seed_enabled or len(scoring.items) == 0:
        return
    result = await container.llm_model_score_repository.seed_many(
        (
            item.model_dump(mode="json", exclude_none=True)
            for item in scoring.items
        ),
        force_refresh=scoring.force_seed_refresh,
    )
    logger.info(
        "frontend.llm_model_scores_seed_applied",
        created=result["created"],
        updated=result["updated"],
        skipped=result["skipped"],
        force_seed_refresh=scoring.force_seed_refresh,
    )


async def on_startup(app: FastAPI, container: FrontendContainer, settings: FrontendSettings) -> None:
    _ = settings
    if is_testing():
        return
    _ = await ensure_system_admin_membership(
        company_repository=container.company_repository,
        subdomain_repository=container.subdomain_repository,
        user_repository=container.user_repository,
    )
    await ensure_demo_company_and_user(
        company_repository=container.company_repository,
        user_repository=container.user_repository,
        subdomain_repository=container.subdomain_repository,
    )
    await _seed_platform_pronunciation_rules(container)
    await _seed_llm_model_scores(container)
    n = await container.billing_service.ensure_settlement_rules_materialized_for_all_companies()
    logger.info("Биллинг: правила settlement проверены/записаны для компаний: %s", n)

    await container.redis_client.connect()
    logger.info("frontend.redis.connected")

    PaymentProviderFactory.initialize()
    await PaymentProviderFactory.seed_access_tokens(container.shared_storage)
    logger.info("Платежные провайдеры инициализированы")
    schedule_docs_assistant_bootstrap(
        app,
        container,
        project_root=Path(__file__).resolve().parents[2],
    )

# Создаем приложение через фабрику (автоматически подключает middleware, контейнер и т.д.)
_frontend_settings = get_frontend_settings()
_frontend_cors_regex = _frontend_settings.cors_allow_origin_regex
_frontend_cors_origins = list(_frontend_settings.cors_allow_origins)
if _frontend_cors_regex is None and _frontend_settings.server.debug and not is_testing():
    _frontend_cors_regex = _FRONTEND_DEV_CORS_ORIGIN_REGEX

app = create_service_app(
    service_name="frontend",
    settings_class=FrontendSettings,
    get_container=get_frontend_container,
    on_startup=on_startup,
    routers=[],
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    pages_routers=[
        auth_router,
        companies_router,
        company_voice_providers_router,
        company_pronunciation_rules_router,
        platform_pronunciation_rules_router,
        voice_providers_catalog_router,
        embed_configs_router,
        public_landing_agents_router,
        public_docs_assistant_router,
        public_search_router,
        public_site_router,
        invites_router,
        team_router,
        api_keys_router,
        billing_router,
        settings_router,
        ai_providers_router,
        search_providers_router,
        services_router,
        scheduler_router,
        leads_router,
        lead_requests_router,
        platform_tracing_router,
        platform_billing_router,
        platform_llm_model_scores_router,
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

# YooMoney и другие провайдеры часто настроены на URL без префикса сервиса (`/api/v1/payments/...`).
# Иначе POST попадает на SPA `GET /{full_path:path}` и даёт 405.
app.include_router(payments_webhook_router, tags=["payments-webhook-root"])

# Монтирование core/frontend (общая библиотека) - СНАЧАЛА монтируем статику!
core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount(
        "/static/core",
        StaticFiles(directory=str(core_frontend_path)),
        name="core-frontend"
    )
    logger.info("frontend.core_lib_mounted", path=str(core_frontend_path))

# Монтирование apps/frontend/ui (само приложение)
ui_path = Path(__file__).parent / "ui"
if ui_path.exists():
    app.mount(
        "/static/frontend",
        StaticFiles(directory=str(ui_path)),
        name="frontend-ui"
    )
    logger.info("frontend.ui_mounted", path=str(ui_path))

# Удаляем дефолтный root endpoint от фабрики - ПОСЛЕ монтирования статики
# (он возвращает {"service": "core", "version": "1.0.0", "status": "running"})
# Заменим его на SPA-резерв ниже
for route in list(app.routes):
    if isinstance(route, Route) and route.path == "/":
        app.routes.remove(route)

@app.get("/api/health")
@app.get("/health")
async def health(container: ContainerDep):
    _ = container
    return build_health_payload(get_frontend_settings())

@app.api_route("/l/{code}", methods=["GET", "HEAD"])
async def resolve_short_link(request: Request, container: ContainerDep, code: str):
    trimmed = code.strip()

    if request.method.upper() == "HEAD":
        row_head = await container.short_link_repository.get_by_code(trimmed)
        if row_head is not None and row_head.kind == SHORT_LINK_KIND_FLOW_PREVIEW_EMBED:
            now = datetime.now(UTC)
            if row_head.expires_at <= now:
                raise HTTPException(status_code=404, detail="Ссылка не найдена или истекла")
            return Response(status_code=200, content=b"")
        target_head = await container.short_link_service.resolve_absolute_redirect_url(trimmed)
        if target_head is None:
            raise HTTPException(status_code=404, detail="Ссылка не найдена или истекла")
        return Response(status_code=200, content=b"")

    row = await container.short_link_repository.delete_by_code_and_kind_returning(
        trimmed, SHORT_LINK_KIND_FLOW_PREVIEW_EMBED
    )
    if row is not None:
        now = datetime.now(UTC)
        if row.expires_at <= now:
            raise HTTPException(status_code=404, detail="Ссылка не найдена или истекла")
        payload = FlowPreviewEmbedPayload.model_validate(row.payload)
        loc_path = f"/flow-preview?h={quote(payload.handoff_id, safe='')}"
        return RedirectResponse(url=_short_link_redirect_location(loc_path), status_code=303)

    target = await container.short_link_service.resolve_absolute_redirect_url(trimmed)
    if target is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена или истекла")
    return RedirectResponse(url=_short_link_redirect_location(target), status_code=303)


@app.api_route("/flow-preview", methods=["GET", "HEAD"])
async def flow_preview_guest_page(request: Request, container: ContainerDep, h: str = ""):
    handoff_id = (h or "").strip()
    if not handoff_id:
        if request.method.upper() == "HEAD":
            return Response(status_code=404, content=b"")
        return _flow_preview_unavailable_response(request)

    if request.method.upper() == "HEAD":
        exists = await peek_flow_preview_handoff(
            redis=container.redis_client,
            handoff_id=handoff_id,
        )
        if not exists:
            return Response(status_code=404, content=b"")
        return Response(status_code=200, content=b"")

    payload = await consume_flow_preview_handoff(
        redis=container.redis_client,
        handoff_id=handoff_id,
    )
    if payload is None:
        return _flow_preview_unavailable_response(request)

    jwt = payload.get("jwt")
    embed_id = payload.get("embed_id")
    flow_id = payload.get("flow_id")
    branch_id = payload.get("branch_id")
    assistant_title = payload.get("assistant_title")
    interface_locale = payload.get("interface_locale")
    flows_base_url = payload.get("flows_base_url")
    platform_ui_origin = payload.get("platform_ui_origin")
    company_id = payload.get("company_id")

    if not isinstance(jwt, str) or not jwt.strip():
        return _flow_preview_unavailable_response(request)
    if not isinstance(embed_id, str) or not embed_id.strip():
        return _flow_preview_unavailable_response(request)
    if not isinstance(flow_id, str) or not flow_id.strip():
        return _flow_preview_unavailable_response(request)
    if not isinstance(branch_id, str) or not branch_id.strip():
        return _flow_preview_unavailable_response(request)
    if not isinstance(flows_base_url, str) or not flows_base_url.strip():
        return _flow_preview_unavailable_response(request)
    if not isinstance(platform_ui_origin, str) or not platform_ui_origin.strip():
        return _flow_preview_unavailable_response(request)
    if not isinstance(company_id, str) or not company_id.strip():
        return _flow_preview_unavailable_response(request)

    if not isinstance(assistant_title, str) or not assistant_title.strip():
        assistant_title = flow_id.strip()
    else:
        assistant_title = assistant_title.strip()

    if not isinstance(interface_locale, str) or not interface_locale.strip():
        interface_locale = "auto"
    else:
        interface_locale = interface_locale.strip()

    base = build_service_base_url(request)
    # Только same-origin `/static/core/...`: страница на нашем домене; CDN-скрипт может быть иной сборки
    # и ломать нативный ESM (bare `@platform/*` без import map).
    script_url = f"{base}/static/core/lib/embed-chat/humanitec-embed-autoload.js"

    html_out = build_flow_preview_guest_html(
        script_url=script_url,
        embed_id=embed_id.strip(),
        flow_id=flow_id.strip(),
        branch_id=branch_id.strip(),
        assistant_title=assistant_title,
        interface_locale=interface_locale,
        flows_base_url=flows_base_url.strip(),
        platform_ui_origin=platform_ui_origin.strip(),
        static_bearer=jwt.strip(),
        company_id=company_id.strip(),
    )
    return Response(content=html_out, media_type="text/html; charset=utf-8")


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
    base_url = get_frontend_public_base_url()
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
    base_url = get_frontend_public_base_url()
    sitemap_xml = _build_sitemap_xml(base_url=base_url)
    return Response(content=sitemap_xml, media_type="application/xml")

@app.get("/llms.txt")
@app.get("/frontend/llms.txt")
async def get_llms_txt(container: ContainerDep) -> PlainTextResponse:
    _ = container
    base_url = get_frontend_public_base_url()
    return PlainTextResponse(content=_build_llms_txt(base_url=base_url))


# SPA-резерв (все неизвестные пути → index.html)
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


app.add_middleware(StaticCoreModuleCorsMiddleware)


if __name__ == "__main__":
    from apps.frontend.config import get_frontend_settings
    from core.app.server import serve

    serve("frontend", "apps.frontend.main:app", get_frontend_settings())
