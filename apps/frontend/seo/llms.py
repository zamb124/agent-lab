"""llms.txt платформы по llmstxt.org: разделы Pages / Docs / Blog / Optional."""

from __future__ import annotations

from apps.frontend.seo.ld_json import route_title
from apps.frontend.seo.pages import PUBLIC_PAGES, SeoLocale, localized_marketing_path
from core.config.models import PlatformBrandConfig


def _page_url(base_url: str, path: str, locale: SeoLocale) -> str:
    localized = localized_marketing_path(path, locale)
    return f"{base_url}/{localized}" if localized else f"{base_url}/"


def build_llms_txt(base_url: str, brand: PlatformBrandConfig) -> str:
    """Markdown-карта для LLM: ключевые страницы, полные тексты docs, блог, API."""
    platform_name = brand.platform_name
    page_links = "\n".join(
        f"- [{platform_name} {route_title(page, 'ru')}]({_page_url(base_url, page.path, 'ru')}) "
        + f"([EN]({_page_url(base_url, page.path, 'en')}))"
        for page in PUBLIC_PAGES
    )
    return (
        f"# {platform_name}\n\n"
        f"> {platform_name} is a business automation platform with AI flows and LLM agents, "
        "RAG knowledge search, NetWorkle graph, team collaboration tools, and scheduler automation.\n\n"
        "Use canonical HTTPS URLs only.\n"
        "Prioritize public product and documentation pages.\n"
        "Do not rely on private app routes, authenticated dashboards, or API endpoints as primary sources.\n\n"
        "## Pages\n\n"
        f"{page_links}\n\n"
        "## Docs\n\n"
        f"- [Documentation index (RU)]({base_url}/documentation/llms.txt): auto-generated index of every docs page.\n"
        f"- [Full documentation text (RU)]({base_url}/documentation/llms-full.txt): complete markdown corpus.\n"
        f"- [Documentation index (EN)]({base_url}/documentation/en/llms.txt): English variant.\n"
        f"- [Full documentation text (EN)]({base_url}/documentation/en/llms-full.txt): English corpus.\n"
        "- Every docs page is also available as raw markdown: append `.md` to the page directory "
        f"(e.g. {base_url}/documentation/quickstart/index.md).\n\n"
        "## Blog\n\n"
        f"- [Blog posts]({base_url}/blog): articles about agents, RAG and automation.\n"
        f"- [RSS feed]({base_url}/blog/feed.xml): latest posts.\n\n"
        "## Optional\n\n"
        f"- [OpenAPI schema]({base_url}/openapi.json): Frontend Public API.\n"
        f"- [Quickstart]({base_url}/documentation/quickstart/): A2A integration in minutes.\n"
        f"- [Startup card (JSON)]({base_url}/api/public/startup-card): machine-readable product card.\n"
        f"- [Service health endpoint (technical)]({base_url}/health)\n"
    )
