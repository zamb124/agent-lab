"""robots.txt платформы: разрешённая публичная зона, запреты приватного и AI-краулеры."""

from __future__ import annotations

# Сервисные префиксы и служебные пути, которые нельзя индексировать.
_DISALLOWED_PREFIXES: tuple[str, ...] = (
    "/api/",
    "/frontend/api/",
    "/auth/",
    "/frontend/api/auth/",
    "/ws/",
    "/frontend/ws/",
    "/crm/",
    "/sync/",
    "/rag/",
    "/flows/",
    "/office/",
    "/documents/",
    "/wiki/",
    "/stock/",
    "/geo/",
    "/scheduler/",
    "/secrets/",
    "/voice/",
    "/search/api/",
    "/browser/",
    "/litserve/",
    "/realtime/",
    "/market/api/",
)

# SPA-маршруты консоли и pre-session: оболочка без контента, индексировать нельзя.
_DISALLOWED_SPA_PATHS: tuple[str, ...] = (
    "/login",
    "/join",
    "/select-company",
    "/dashboard",
    "/services",
    "/team",
    "/access",
    "/namespaces",
    "/api-keys",
    "/company-variables",
    "/company-voice-providers",
    "/embed-configs",
    "/billing",
    "/scheduler-tasks",
    "/settings",
    "/lead-requests",
    "/platform-tracing",
    "/crawl-report",
    "/platform-billing",
    "/design-system",
    "/l/",
    "/flow-preview",
    "/flow-session-share",
    "/flow-embed-page",
)

# LLM/AI-краулеры: явные секции документируют разрешение индексировать контент
# для обучения и RAG-ответов (статус на начало 2026).
_AI_USER_AGENTS: tuple[str, ...] = (
    "GPTBot",
    "OAI-SearchBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-User",
    "Claude-SearchBot",
    "PerplexityBot",
    "Perplexity-User",
    "Google-Extended",
    "Applebot-Extended",
    "CCBot",
    "Bytespider",
    "Amazonbot",
    "meta-externalagent",
    "FacebookBot",
    "MistralAI-User",
    "cohere-ai",
    "cohere-training-data-crawler",
    "DuckAssistBot",
    "YouBot",
    "ImagesiftBot",
    "PanguBot",
    "Kangaroo Bot",
    "Diffbot",
    "AI2Bot",
    "Ai2Bot-Dolma",
    "Timpibot",
    "VelenPublicWebCrawler",
    "Webzio-Extended",
    "Omgilibot",
    "Omgili",
)


def build_robots_txt(base_url: str) -> str:
    """Allow публичной зоны для всех; запреты приватных путей; sitemap-index."""
    # Приватные SPA-пути запрещаем и в /en-зеркале — обе локали существуют,
    # а /en/<private> отдаёт ту же noindex-оболочку.
    disallowed = (
        *_DISALLOWED_PREFIXES,
        *_DISALLOWED_SPA_PATHS,
        *(f"/en{p}" for p in _DISALLOWED_SPA_PATHS),
    )
    disallows = "\n".join(f"Disallow: {path}" for path in disallowed)
    sections = [
        "User-agent: *\nAllow: /\n" + disallows + "\n",
    ]
    for agent in _AI_USER_AGENTS:
        sections.append(f"User-agent: {agent}\nAllow: /\n{disallows}\n")
    sections.append(f"Sitemap: {base_url}/sitemap.xml\n")
    return "\n".join(sections)
