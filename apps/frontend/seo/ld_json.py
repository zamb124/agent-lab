"""JSON-LD графы публичных страниц: Organization/WebSite/SoftwareApplication/FAQ/Breadcrumb.

Тексты берутся из тех же i18n-бандлов, что видит пользователь
(``core/i18n/translations/<locale>/``), — канонических дублей не создаём.
"""

from __future__ import annotations

import json
from functools import lru_cache

from apps.frontend.seo.blog_files import repo_root
from apps.frontend.seo.pages import (
    PUBLIC_PRODUCT_KEYS,
    PublicPage,
    SeoLocale,
    localized_marketing_path,
    public_page_for_path,
)
from core.config.models import PlatformBrandConfig
from core.types import JsonObject, parse_json_object

LOGO_PATH = "/static/core/assets/service_logos/frontend_logo.svg"
OG_IMAGE_PATH = "/static/frontend/assets/images/main_img.png"


@lru_cache(maxsize=8)
def _translations(namespace: str, locale: SeoLocale) -> JsonObject:
    path = repo_root() / "core" / "i18n" / "translations" / locale / f"{namespace}.json"
    if not path.is_file():
        return {}
    return parse_json_object(path.read_text(encoding="utf-8"))


def _bundle_object(bundle: JsonObject, key: str) -> JsonObject:
    value = bundle.get(key)
    if isinstance(value, dict):
        return value
    return {}


def route_title(page: PublicPage, locale: SeoLocale) -> str:
    """Локализованный nav-тайтл — тот же ``routes.<route_key>``, что видит SPA.

    Ключа нет → KeyError: гейт ``public_pages_canon`` ловит пропуск в CI,
    рантайм честно падает в postprocess (alert + SPA-fallback), а не отдаёт
    JSON-LD с деградированным тайтлом.
    """
    routes = _bundle_object(_translations("frontend", locale), "routes")
    return str(routes[page.route_key])


def _product_bundle(page: PublicPage, locale: SeoLocale) -> JsonObject:
    """Запись ``frontend_products.<key>``: ключ — последний сегмент ``products/<key>``."""
    return _bundle_object(
        _translations("frontend_products", locale), page.path.rsplit("/", 1)[-1]
    )


def product_marketing_names(locale: SeoLocale) -> tuple[str, ...]:
    """Маркетинговые имена продуктов (``AI Studio``, ``NetWorkle``…) из
    ``frontend_products.<key>.meta_title`` — первый сегмент до `` — ``.
    Список деривится из ``PUBLIC_PRODUCT_KEYS``: новая продуктовая страница
    попадает сюда автоматически."""
    bundle = _translations("frontend_products", locale)
    return tuple(
        str(_bundle_object(bundle, key)["meta_title"]).split(" — ", 1)[0]
        for key in PUBLIC_PRODUCT_KEYS
    )


def _page_url(seo_base_url: str, path: str, locale: SeoLocale) -> str:
    localized = localized_marketing_path(path, locale)
    return f"{seo_base_url}/{localized}" if localized else f"{seo_base_url}/"


def _organization(brand: PlatformBrandConfig, seo_base_url: str) -> JsonObject:
    return {
        "@type": "Organization",
        "@id": f"{seo_base_url}/#organization",
        "name": brand.platform_name,
        "url": f"{seo_base_url}/",
        "logo": f"{seo_base_url}{LOGO_PATH}",
    }


def _website(brand: PlatformBrandConfig, seo_base_url: str, locale: SeoLocale) -> JsonObject:
    products = ", ".join(product_marketing_names(locale))
    description = (
        f"{brand.platform_name} — business automation platform: {products}."
        if locale == "en"
        else f"{brand.platform_name} — платформа автоматизации бизнеса: {products}."
    )
    return {
        "@type": "WebSite",
        "@id": f"{seo_base_url}/#website",
        "name": brand.platform_name,
        "url": f"{seo_base_url}/",
        "inLanguage": locale,
        "description": description,
        "publisher": {"@id": f"{seo_base_url}/#organization"},
    }


def _software_app(
    brand: PlatformBrandConfig,
    seo_base_url: str,
    page: PublicPage,
    locale: SeoLocale,
) -> JsonObject:
    if page.kind == "product":
        product = _product_bundle(page, locale)
        title = str(product["meta_title"])
        description = str(product["meta_description"])
    else:
        title = brand.platform_name
        products = ", ".join(product_marketing_names(locale))
        description = (
            f"Business automation platform: {products}."
            if locale == "en"
            else f"Платформа автоматизации бизнеса: {products}."
        )
    app: JsonObject = {
        "@type": "SoftwareApplication",
        "name": title,
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Web",
        "url": _page_url(seo_base_url, page.path, locale),
        "description": description,
        "inLanguage": locale,
        "publisher": {"@id": f"{seo_base_url}/#organization"},
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"},
    }
    return app


def _faq_graph(locale: SeoLocale) -> JsonObject | None:
    bundle = _translations("landing", locale)
    faq = bundle.get("faq")
    if not isinstance(faq, dict):
        return None
    slots: list[tuple[str, str]] = []
    i = 1
    while True:
        q = faq.get(f"slot{i}_q")
        a = faq.get(f"slot{i}_a")
        if not isinstance(q, str) or not isinstance(a, str) or not q.strip() or not a.strip():
            break
        slots.append((q, a))
        i += 1
    if not slots:
        return None
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in slots
        ],
    }


def _breadcrumb(seo_base_url: str, page: PublicPage, locale: SeoLocale) -> JsonObject:
    routes = _bundle_object(_translations("frontend", locale), "routes")
    title = route_title(page, locale)
    items: list[JsonObject] = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": str(routes["landing"]),
            "item": _page_url(seo_base_url, "", locale),
        },
    ]
    # Промежуточные уровни — только реальные публичные страницы реестра
    # (``products``, ``demo``…): фейковый уровень со ссылкой на главную
    # не добавляем; появится листинг — crumb деривнётся сам.
    prefix = ""
    for segment in page.path.split("/")[:-1]:
        prefix = f"{prefix}/{segment}".strip("/")
        parent = public_page_for_path(prefix)
        if parent is not None:
            items.append(
                {
                    "@type": "ListItem",
                    "position": len(items) + 1,
                    "name": route_title(parent, locale),
                    "item": _page_url(seo_base_url, parent.path, locale),
                }
            )
    items.append(
        {
            "@type": "ListItem",
            "position": len(items) + 1,
            "name": title,
            "item": _page_url(seo_base_url, page.path, locale),
        }
    )
    return {"@type": "BreadcrumbList", "itemListElement": items}


def build_ld_graph(
    page: PublicPage, *, brand: PlatformBrandConfig, seo_base_url: str, locale: SeoLocale
) -> JsonObject | None:
    """JSON-LD @graph страницы по её ``ld`` видам; ``None`` — граф не нужен."""
    if not page.ld:
        return None
    graph: list[JsonObject] = []
    if "website" in page.ld or "organization" in page.ld:
        graph.append(_website(brand, seo_base_url, locale))
        graph.append(_organization(brand, seo_base_url))
    if "software_app" in page.ld:
        graph.append(_software_app(brand, seo_base_url, page, locale))
    if "faq" in page.ld:
        faq = _faq_graph(locale)
        if faq is not None:
            graph.append(faq)
    if "blog" in page.ld:
        graph.append(
            {
                "@type": "Blog",
                "name": f"{brand.platform_name} Blog"
                if locale == "en"
                else f"Блог {brand.platform_name}",
                "url": _page_url(seo_base_url, page.path, locale),
                "inLanguage": locale,
                "publisher": {"@id": f"{seo_base_url}/#organization"},
            }
        )
    if "breadcrumb" in page.ld:
        graph.append(_breadcrumb(seo_base_url, page, locale))
    if not graph:
        return None
    return {"@context": "https://schema.org", "@graph": graph}


def render_ld_script(
    page: PublicPage, *, brand: PlatformBrandConfig, seo_base_url: str, locale: SeoLocale
) -> str:
    """``<script type="application/ld+json">…</script>`` для вставки в head."""
    graph = build_ld_graph(page, brand=brand, seo_base_url=seo_base_url, locale=locale)
    if graph is None:
        return ""
    body = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json" id="seo-ld-json">{body}</script>'


def build_ld_json(
    page: PublicPage, *, brand: PlatformBrandConfig, seo_base_url: str, locale: SeoLocale
) -> str:
    """Alias для тестов: JSON-строка графа (без script-обёртки)."""
    graph = build_ld_graph(page, brand=brand, seo_base_url=seo_base_url, locale=locale)
    return "" if graph is None else json.dumps(graph, ensure_ascii=False)
