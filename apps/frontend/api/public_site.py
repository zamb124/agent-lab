"""
Публичные данные для лендинга: юридические реквизиты, маркетинг, каталог статей, карточка для каталогов.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from apps.frontend.cookie_consent import COOKIE_CONSENT_TEXT_VERSION
from apps.frontend.di import Di
from apps.frontend.models import (
    CookieConsentCreateBody,
    CookieConsentRecord,
    PublicBlogListResponse,
    PublicBlogPost,
    PublicSiteBundle,
    PublicStartupCard,
)
from apps.frontend.seo.blog_files import blog_body_path, read_blog_body, read_blog_index
from apps.frontend.seo.ld_json import product_marketing_names
from apps.frontend.services.cookie_consent_service import analytics_configured
from core.platform_brand.resolver import resolve_brand, resolve_public_base_url
from core.types import JsonObject
from core.websocket import WsCommandError

router = APIRouter(prefix="/api/public", tags=["public-site"])


def _blog_post_model(entry: JsonObject, platform_name: str) -> PublicBlogPost | None:
    """PublicBlogPost из карточки index.json + body-фрагментов seo-dist.

    ``None`` — body-файла нет (событие ``seo.blog_body_missing`` уже залогировано
    в ``read_blog_body``): список пропускает битый пост, detail отвечает 404.
    """
    slug = str(entry["slug"])
    body_ru = read_blog_body(slug)
    if body_ru is None:
        return None
    body_en_path = blog_body_path(slug, "en")
    body_en = body_en_path.read_text(encoding="utf-8") if body_en_path.is_file() else body_ru
    return PublicBlogPost(
        slug=slug,
        title_ru=str(entry["title_ru"]).replace("{platformName}", platform_name),
        title_en=str(entry["title_en"]).replace("{platformName}", platform_name),
        summary_ru=str(entry["summary_ru"]).replace("{platformName}", platform_name),
        summary_en=str(entry["summary_en"]).replace("{platformName}", platform_name),
        body_ru=body_ru.replace("{platformName}", platform_name),
        body_en=body_en.replace("{platformName}", platform_name),
    )


@router.get("/site-bundle", response_model=PublicSiteBundle)
async def get_site_bundle(request: Request, di: Di) -> PublicSiteBundle:
    _ = di
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise WsCommandError("ws_invalid_payload", "Host header is required", error_code="ws_invalid_payload")
    brand = resolve_brand(str(host).strip())
    return PublicSiteBundle(
        legal=brand.legal,
        marketing=brand.public_site,
        cookie_consent_text_version=COOKIE_CONSENT_TEXT_VERSION,
        analytics_configured=analytics_configured(brand.public_site),
    )


@router.post("/cookie-consent", response_model=CookieConsentRecord, tags=["public-site", "public"])
async def record_cookie_consent(
    request: Request,
    body: CookieConsentCreateBody,
    di: Di,
) -> CookieConsentRecord:
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise WsCommandError("ws_invalid_payload", "Host header is required", error_code="ws_invalid_payload")
    brand = resolve_brand(str(host).strip())
    return await di.cookie_consent_service.record(body, request=request, brand=brand)


@router.get("/blog", response_model=PublicBlogListResponse)
async def list_public_blog_posts(request: Request, di: Di) -> PublicBlogListResponse:
    _ = di
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise WsCommandError("ws_invalid_payload", "Host header is required", error_code="ws_invalid_payload")
    brand = resolve_brand(str(host).strip())
    items = tuple(
        post
        for entry in read_blog_index()
        if (post := _blog_post_model(entry, brand.platform_name)) is not None
    )
    return PublicBlogListResponse(items=items)


@router.get("/blog/post", response_model=PublicBlogPost)
async def get_public_blog_post(
    request: Request,
    di: Di,
    slug: Annotated[str, Query(min_length=1)],
) -> PublicBlogPost:
    _ = di
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise WsCommandError("ws_invalid_payload", "Host header is required", error_code="ws_invalid_payload")
    brand = resolve_brand(str(host).strip())
    for entry in read_blog_index():
        if entry.get("slug") == slug:
            post = _blog_post_model(entry, brand.platform_name)
            if post is not None:
                return post
            break
    raise WsCommandError("not_found", "Post not found", error_code="not_found")


@router.get("/startup-card", response_model=PublicStartupCard)
async def get_startup_card(request: Request, di: Di) -> PublicStartupCard:
    """Карточка продукта для внешних каталогов и форм submit startup."""
    _ = di
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise WsCommandError("ws_invalid_payload", "Host header is required", error_code="ws_invalid_payload")
    brand = resolve_brand(str(host).strip())
    base_url = resolve_public_base_url(str(host).strip())
    return PublicStartupCard(
        name=brand.platform_name,
        tagline_ru="Платформа автоматизации бизнеса: AI-агенты, база знаний, CRM-граф, чат и документы.",
        tagline_en="Business automation platform: AI agents, knowledge base, CRM graph, chat, and documents.",
        website_url=base_url,
        products=product_marketing_names("en"),
        deployment_modes=("cloud", "hybrid", "on-premise"),
        logo_url=f"{base_url}/static/core/assets/service_logos/frontend_logo.svg",
    )
