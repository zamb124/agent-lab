"""
Публичные данные для лендинга: юридические реквизиты, маркетинг, каталог статей, карточка для каталогов.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.frontend.config import get_frontend_public_base_url, get_frontend_settings
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    PublicBlogListResponse,
    PublicBlogPost,
    PublicSiteBundle,
    PublicStartupCard,
)

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
            "Humanitec объединяет Knowledge Base, AI Studio и каналы связи так, что эскалация к человеку остаётся "
            "явной частью процесса.</p>"
            "<p>На практике это означает предсказуемые ответы по базе знаний, журналирование и возможность "
            "быстро обновить источники без передеплоя кода.</p>"
        ),
        body_en=(
            "<p>RAG lets answers cite your documents and policies instead of generic model knowledge. "
            "Humanitec connects Knowledge Base, AI Studio, and channels so human escalation stays an explicit "
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


@router.get("/site-bundle", response_model=PublicSiteBundle)
async def get_site_bundle(container: ContainerDep) -> PublicSiteBundle:
    _ = container
    settings = get_frontend_settings()
    return PublicSiteBundle(legal=settings.legal, marketing=settings.public_site)


@router.get("/blog", response_model=PublicBlogListResponse)
async def list_public_blog_posts(container: ContainerDep) -> PublicBlogListResponse:
    _ = container
    return PublicBlogListResponse(items=_BLOG_POSTS)


@router.get("/blog/post", response_model=PublicBlogPost)
async def get_public_blog_post(
    container: ContainerDep,
    slug: Annotated[str, Query(min_length=1)],
) -> PublicBlogPost:
    _ = container
    for post in _BLOG_POSTS:
        if post.slug == slug:
            return post
    raise HTTPException(status_code=404, detail="Post not found")


@router.get("/startup-card", response_model=PublicStartupCard)
async def get_startup_card(container: ContainerDep) -> PublicStartupCard:
    """Карточка продукта для внешних каталогов и форм submit startup."""
    _ = container
    base_url = get_frontend_public_base_url()
    return PublicStartupCard(
        name="Humanitec",
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
