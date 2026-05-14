"""
Публичные данные для лендинга: юридические реквизиты, маркетинг, каталог статей, карточка для каталогов.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from apps.frontend.config import get_frontend_settings
from apps.frontend.dependencies import ContainerDep

router = APIRouter(prefix="/api/public", tags=["public-site"])

_BLOG_POSTS: tuple[dict[str, Any], ...] = (
    {
        "slug": "ai-agent-support-rag",
        "title_ru": "ИИ-поддержка 24/7 на базе корпоративных регламентов",
        "title_en": "24/7 AI support grounded in corporate policies",
        "summary_ru": "Как связать RAG с очередью оператора и сократить типовые обращения без потери контроля качества.",
        "summary_en": "How to combine RAG with an operator queue and cut repetitive tickets without losing quality control.",
        "body_ru": (
            "<p>RAG позволяет отвечать опираясь на ваши документы и регламенты, а не на «общие знания» модели. "
            "Humanitec объединяет Knowledge Base, AI Studio и каналы связи так, что эскалация к человеку остаётся "
            "явной частью процесса.</p>"
            "<p>На практике это означает предсказуемые ответы по базе знаний, журналирование и возможность "
            "быстро обновить источники без передеплоя кода.</p>"
        ),
        "body_en": (
            "<p>RAG lets answers cite your documents and policies instead of generic model knowledge. "
            "Humanitec connects Knowledge Base, AI Studio, and channels so human escalation stays an explicit "
            "part of the flow.</p>"
            "<p>In practice you get predictable answers from your knowledge base, logging, and fast source updates "
            "without redeploying code.</p>"
        ),
    },
    {
        "slug": "platform-five-products",
        "title_ru": "Пять продуктов одной платформы: зачем это бизнесу",
        "title_en": "Five products in one platform: why it matters for business",
        "summary_ru": "AI Studio, Knowledge Base, NetWorkle, Sync и Документы — как связка снижает стоимость владения инструментами.",
        "summary_en": "AI Studio, Knowledge Base, NetWorkle, Sync, and Documents — how the bundle lowers total cost of ownership.",
        "body_ru": (
            "<p>Когда агенты, база знаний, CRM-граф, чат и офисные документы живут в одном контуре, не нужно "
            "собирать десяток подписок и отдельных интеграций. Единый вход и общая модель компании упрощают "
            "безопасность и онбординг.</p>"
        ),
        "body_en": (
            "<p>When agents, knowledge base, CRM graph, chat, and office documents share one perimeter, you avoid "
            "a patchwork of subscriptions and glue integrations. A single entry point and company model simplify "
            "security and onboarding.</p>"
        ),
    },
)


@router.get("/site-bundle")
async def get_site_bundle(container: ContainerDep) -> JSONResponse:
    _ = container
    settings = get_frontend_settings()
    return JSONResponse(
        content={
            "legal": settings.legal.model_dump(),
            "marketing": settings.public_site.model_dump(),
        }
    )


@router.get("/blog")
async def list_public_blog_posts(container: ContainerDep) -> JSONResponse:
    _ = container
    items = []
    for row in _BLOG_POSTS:
        items.append(
            {
                "slug": row["slug"],
                "title_ru": row["title_ru"],
                "title_en": row["title_en"],
                "summary_ru": row["summary_ru"],
                "summary_en": row["summary_en"],
            }
        )
    return JSONResponse(content={"items": items})


@router.get("/blog/post")
async def get_public_blog_post(container: ContainerDep, slug: str = Query(..., min_length=1)) -> JSONResponse:
    _ = container
    for row in _BLOG_POSTS:
        if row["slug"] == slug:
            return JSONResponse(content=dict(row))
    raise HTTPException(status_code=404, detail="Post not found")


@router.get("/startup-card")
async def get_startup_card(container: ContainerDep) -> JSONResponse:
    """Карточка продукта для внешних каталогов и форм submit startup."""
    _ = container
    settings = get_frontend_settings()
    base = (settings.server.platform_public_base_url or "").rstrip("/")
    return JSONResponse(
        content={
            "name": "Humanitec",
            "tagline_ru": "Платформа автоматизации бизнеса: AI-агенты, база знаний, CRM-граф, чат и документы.",
            "tagline_en": "Business automation platform: AI agents, knowledge base, CRM graph, chat, and documents.",
            "website_url": base if base else None,
            "products": [
                "AI Studio",
                "Knowledge Base",
                "NetWorkle",
                "Sync",
                "Documents",
            ],
            "deployment_modes": ["cloud", "hybrid", "on-premise"],
            "logo_url": f"{base}/static/core/assets/service_logos/frontend_logo.svg" if base else None,
        }
    )
