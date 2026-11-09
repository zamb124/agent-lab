"""Реестр публичных индексируемых страниц — единый источник sitemap, llms.txt и снапшотов.

Любая новая публичная маркетинговая страница добавляется сюда (и как public route
в ``frontend-app.ts``); гейт ``public_pages_canon`` проверяет паритет двух списков.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PublicPageKind = Literal[
    "landing", "product", "legal", "support", "demo", "blog", "about", "search"
]

LdKind = Literal["website", "organization", "software_app", "faq", "blog", "breadcrumb"]

SeoLocale = Literal["ru", "en"]

SEO_LOCALES: tuple[SeoLocale, ...] = ("ru", "en")


@dataclass(frozen=True)
class PublicPage:
    """Одна индексируемая страница маркетинга.

    ``path`` — без ведущего слэша; ``""`` — корень лендинга.
    ``route_key`` — ключ маршрута из ``FRONTEND_ROUTES`` (``product-rag``,
    ``cookie-consent``…): по нему берётся локализованный nav-тайтл из
    ``i18n routes.*`` и гейт сверяет паритет key↔path.
    ``ld`` — типы JSON-LD сущностей, которые снапшот-конвейер вставляет в head.
    ``wait_selector`` — маркер готовности контента для пререндера (Playwright
    pierces shadow DOM); новая страница без ``landing-footer`` задаёт свой.
    """

    path: str
    kind: PublicPageKind
    priority: str
    changefreq: str
    og_image: bool
    ld: tuple[LdKind, ...]
    route_key: str
    wait_selector: str = "landing-footer"


PUBLIC_PAGES: tuple[PublicPage, ...] = (
    PublicPage(
        "", "landing", "0.90", "weekly", True,
        ("website", "organization", "software_app", "faq"), route_key="landing",
    ),
    PublicPage("search", "search", "0.60", "weekly", False, ("website",), route_key="search"),
    PublicPage(
        "products/agents", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-agents",
    ),
    PublicPage(
        "products/rag", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-rag",
    ),
    PublicPage(
        "products/crm", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-crm",
    ),
    PublicPage(
        "products/sync", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-sync",
    ),
    PublicPage(
        "products/documents", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-documents",
    ),
    PublicPage(
        "products/geo", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-geo",
    ),
    PublicPage(
        "products/wiki", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-wiki",
    ),
    PublicPage(
        "products/shop", "product", "0.90", "weekly", True,
        ("software_app", "breadcrumb"), route_key="product-shop",
    ),
    PublicPage("policy", "legal", "0.30", "monthly", False, (), route_key="policy"),
    PublicPage("terms", "legal", "0.30", "monthly", False, (), route_key="terms"),
    PublicPage("cookies", "legal", "0.30", "monthly", False, (), route_key="cookies"),
    PublicPage(
        "consent/cookies", "legal", "0.30", "monthly", False, (), route_key="cookie-consent"
    ),
    PublicPage(
        "support", "support", "0.65", "monthly", False, ("breadcrumb",), route_key="support"
    ),
    PublicPage(
        "demo/digital-workers", "demo", "0.70", "weekly", True,
        ("software_app", "breadcrumb"), route_key="digital-workers",
    ),
    PublicPage(
        "blog", "blog", "0.60", "weekly", False, ("blog", "breadcrumb"), route_key="blog"
    ),
    PublicPage(
        "about", "about", "0.55", "monthly", False,
        ("organization", "breadcrumb"), route_key="about",
    ),
    PublicPage(
        "roadmap", "about", "0.55", "monthly", False, ("breadcrumb",), route_key="roadmap"
    ),
)

PUBLIC_PAGE_PATHS: frozenset[str] = frozenset(page.path for page in PUBLIC_PAGES)


def public_page_for_path(path: str) -> PublicPage | None:
    """Запись реестра для пути без ведущего слэша; ``None`` — не индексируемый маршрут."""
    normalized = path.strip("/")
    for page in PUBLIC_PAGES:
        if page.path == normalized:
            return page
    return None


def localized_marketing_path(path: str, locale: SeoLocale) -> str:
    """Публичный URL-путь в локали: ``products/rag`` → ``en/products/rag`` для en."""
    normalized = path.strip("/")
    if locale == "en":
        return f"en/{normalized}" if normalized else "en"
    return normalized
