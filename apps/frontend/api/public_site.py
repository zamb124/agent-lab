"""
Публичные данные для лендинга: юридические реквизиты, маркетинг, каталог статей, карточка для каталогов.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    PublicBlogListResponse,
    PublicBlogPost,
    PublicSiteBundle,
    PublicStartupCard,
)
from core.platform_brand.resolver import resolve_brand, resolve_public_base_url

router = APIRouter(prefix="/api/public", tags=["public-site"])

_BLOG_POSTS: tuple[PublicBlogPost, ...] = (
    PublicBlogPost(
        slug="ai-agent-support-rag",
        title_ru="ИИ-поддержка 24/7 на базе корпоративных регламентов",
        title_en="24/7 AI support grounded in corporate policies",
        summary_ru="Как связать RAG с очередью оператора и сократить типовые обращения без потери контроля качества.",
        summary_en="How to combine RAG with an operator queue and cut repetitive tickets without losing quality control.",
        body_ru=(
            "<p>RAG позволяет отвечать опираясь на ваши документы и регламенты, а не на «общие знания» модели. "
            "{platformName} объединяет Knowledge Base, AI Studio и каналы связи так, что эскалация к человеку остаётся "
            "явной частью процесса.</p>"
            "<p>На практике это означает предсказуемые ответы по базе знаний, журналирование и возможность "
            "быстро обновить источники без передеплоя кода.</p>"
        ),
        body_en=(
            "<p>RAG lets answers cite your documents and policies instead of generic model knowledge. "
            "{platformName} connects Knowledge Base, AI Studio, and channels so human escalation stays an explicit "
            "part of the flow.</p>"
            "<p>In practice you get predictable answers from your knowledge base, logging, and fast source updates "
            "without redeploying code.</p>"
        ),
    ),
    PublicBlogPost(
        slug="platform-five-products",
        title_ru="Пять продуктов одной платформы: зачем это бизнесу",
        title_en="Five products in one platform: why it matters for business",
        summary_ru="AI Studio, Knowledge Base, NetWorkle, Sync и Документы — как связка снижает стоимость владения инструментами.",
        summary_en="AI Studio, Knowledge Base, NetWorkle, Sync, and Documents — how the bundle lowers total cost of ownership.",
        body_ru=(
            "<p>Когда агенты, база знаний, CRM-граф, чат и офисные документы живут в одном контуре, не нужно "
            "собирать десяток подписок и отдельных интеграций. Единый вход и общая модель компании упрощают "
            "безопасность и онбординг.</p>"
        ),
        body_en=(
            "<p>When agents, knowledge base, CRM graph, chat, and office documents share one perimeter, you avoid "
            "a patchwork of subscriptions and glue integrations. A single entry point and company model simplify "
            "security and onboarding.</p>"
        ),
    ),
)


def _apply_platform_name_to_post(post: PublicBlogPost, platform_name: str) -> PublicBlogPost:
    return post.model_copy(
        update={
            "body_ru": post.body_ru.replace("{platformName}", platform_name),
            "body_en": post.body_en.replace("{platformName}", platform_name),
        }
    )


@router.get("/site-bundle", response_model=PublicSiteBundle)
async def get_site_bundle(request: Request, container: ContainerDep) -> PublicSiteBundle:
    _ = container
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise HTTPException(status_code=400, detail="Host header is required")
    brand = resolve_brand(str(host).strip())
    return PublicSiteBundle(legal=brand.legal, marketing=brand.public_site)


@router.get("/blog", response_model=PublicBlogListResponse)
async def list_public_blog_posts(request: Request, container: ContainerDep) -> PublicBlogListResponse:
    _ = container
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise HTTPException(status_code=400, detail="Host header is required")
    brand = resolve_brand(str(host).strip())
    items = tuple(_apply_platform_name_to_post(post, brand.platform_name) for post in _BLOG_POSTS)
    return PublicBlogListResponse(items=items)


@router.get("/blog/post", response_model=PublicBlogPost)
async def get_public_blog_post(
    request: Request,
    container: ContainerDep,
    slug: Annotated[str, Query(min_length=1)],
) -> PublicBlogPost:
    _ = container
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise HTTPException(status_code=400, detail="Host header is required")
    brand = resolve_brand(str(host).strip())
    for post in _BLOG_POSTS:
        if post.slug == slug:
            return _apply_platform_name_to_post(post, brand.platform_name)
    raise HTTPException(status_code=404, detail="Post not found")


@router.get("/startup-card", response_model=PublicStartupCard)
async def get_startup_card(request: Request, container: ContainerDep) -> PublicStartupCard:
    """Карточка продукта для внешних каталогов и форм submit startup."""
    _ = container
    host = request.headers.get("host")
    if host is None or not str(host).strip():
        raise HTTPException(status_code=400, detail="Host header is required")
    brand = resolve_brand(str(host).strip())
    base_url = resolve_public_base_url(str(host).strip())
    return PublicStartupCard(
        name=brand.platform_name,
        tagline_ru="Платформа автоматизации бизнеса: AI-агенты, база знаний, CRM-граф, чат и документы.",
        tagline_en="Business automation platform: AI agents, knowledge base, CRM graph, chat, and documents.",
        website_url=base_url,
        products=(
            "AI Studio",
            "Knowledge Base",
            "NetWorkle",
            "Sync",
            "Documents",
        ),
        deployment_modes=("cloud", "hybrid", "on-premise"),
        logo_url=f"{base_url}/static/core/assets/service_logos/frontend_logo.svg",
    )
