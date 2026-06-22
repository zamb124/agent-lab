"""Compiled URL include/exclude filter for crawl discovery."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from core.crawl.models import CrawlDomain, CrawlProfile


class CrawlUrlFilter:
    """Decides which discovered URLs are eligible for crawling.

    Правила: URL отклоняется, если его расширение в exclude_extensions,
    путь матчит любой exclude-паттерн, либо (при непустом include) ни один
    include-паттерн не совпал. include по умолчанию пуст — пропускаем всё, что
    не отклонено exclude-правилами.
    """

    def __init__(
        self,
        *,
        include_patterns: list[str],
        exclude_patterns: list[str],
        exclude_extensions: list[str],
    ) -> None:
        self._include: list[re.Pattern[str]] = _compile_patterns(include_patterns)
        self._exclude: list[re.Pattern[str]] = _compile_patterns(exclude_patterns)
        normalized_extensions = sorted({ext.strip().lower().lstrip(".") for ext in exclude_extensions if ext.strip()})
        self._extension_re: re.Pattern[str] | None = None
        if normalized_extensions:
            self._extension_re = re.compile(
                r"\.(" + "|".join(re.escape(ext) for ext in normalized_extensions) + r")$",
                re.IGNORECASE,
            )

    def allows(self, url: str) -> bool:
        path = urlsplit(url).path
        if self._extension_re is not None and self._extension_re.search(url):
            return False
        for pattern in self._exclude:
            if pattern.search(path):
                return False
        if not self._include:
            return True
        return any(pattern.search(path) for pattern in self._include)


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for raw in patterns:
        pattern = raw.strip()
        if not pattern:
            continue
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            raise ValueError(f"invalid crawl url pattern: {pattern!r}: {exc}") from exc
    return compiled


def build_url_filter(profile: CrawlProfile, domain: CrawlDomain) -> CrawlUrlFilter:
    """Собирает фильтр: per-domain паттерны имеют приоритет над профильными."""
    include_patterns = domain.include_url_patterns or profile.include_url_patterns
    exclude_patterns = [*profile.exclude_url_patterns, *domain.exclude_url_patterns]
    return CrawlUrlFilter(
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        exclude_extensions=profile.exclude_extensions,
    )
