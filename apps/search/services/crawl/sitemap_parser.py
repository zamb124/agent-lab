"""Discover sitemap URLs for a domain."""

from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

from core.crawl.models import SitemapEntry
from core.http import get_httpx_client

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
_DENY_PATH_RE = re.compile(r"/(cart|checkout|login|auth|search)(/|$)", re.IGNORECASE)
_DENY_EXT_RE = re.compile(r"\.(pdf|zip|jpg|jpeg|png|gif)$", re.IGNORECASE)


class SitemapDiscoveryError(Exception):
    pass


def _same_domain(url: str, domain: str) -> bool:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host == domain or host.endswith(f".{domain}")


def _parse_lastmod(raw: str | None) -> datetime | None:
    if raw is None or not raw.strip():
        return None
    try:
        return parsedate_to_datetime(raw.strip())
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_sitemap_xml(content: bytes, domain: str) -> list[SitemapEntry]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return []
    tag = root.tag.lower()
    if tag.endswith("sitemapindex"):
        return []
    entries: list[SitemapEntry] = []
    for url_node in root.findall(".//sm:url", _SITEMAP_NS):
        loc_node = url_node.find("sm:loc", _SITEMAP_NS)
        if loc_node is None or loc_node.text is None:
            continue
        url = loc_node.text.strip()
        if not _same_domain(url, domain):
            continue
        if _DENY_EXT_RE.search(url) or _DENY_PATH_RE.search(urlparse(url).path):
            continue
        lastmod_node = url_node.find("sm:lastmod", _SITEMAP_NS)
        lastmod = _parse_lastmod(lastmod_node.text if lastmod_node is not None else None)
        entries.append(SitemapEntry(url=url, lastmod=lastmod))
    return entries


def _append_entries(
    collected: list[SitemapEntry],
    entries: list[SitemapEntry],
    *,
    max_urls: int,
) -> bool:
    if not entries:
        return False
    remaining = max_urls - len(collected)
    if remaining <= 0:
        return True
    if len(entries) <= remaining:
        collected.extend(entries)
        return len(collected) >= max_urls
    collected.extend(entries[:remaining])
    return True


async def discover_sitemap_urls(
    domain: str,
    *,
    timeout_seconds: float,
    max_urls: int,
    max_sitemap_bytes: int,
) -> list[SitemapEntry]:
    if max_urls < 1:
        raise ValueError("max_urls must be >= 1")
    if max_sitemap_bytes < 1:
        raise ValueError("max_sitemap_bytes must be >= 1")
    normalized_domain = domain.strip().lower()
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]
    sitemap_urls: list[str] = []
    robots_url = f"https://{normalized_domain}/robots.txt"
    async with get_httpx_client(timeout=timeout_seconds, follow_redirects=True) as client:
        robots_response = await client.get(robots_url)
        if robots_response.status_code == 200:
            for line in robots_response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    candidate = line.split(":", 1)[1].strip()
                    if candidate:
                        sitemap_urls.append(candidate)
        if not sitemap_urls:
            sitemap_urls.append(f"https://{normalized_domain}/sitemap.xml")

        collected: list[SitemapEntry] = []
        seen_sitemaps: set[str] = set()
        limit_reached = False
        for sitemap_url in sitemap_urls:
            if limit_reached:
                break
            if sitemap_url in seen_sitemaps:
                continue
            seen_sitemaps.add(sitemap_url)
            response = await client.get(sitemap_url)
            if response.status_code >= 400:
                continue
            if len(response.content) > max_sitemap_bytes:
                continue
            entries = _parse_sitemap_xml(response.content, normalized_domain)
            if not entries and response.content:
                try:
                    index_root = ElementTree.fromstring(response.content)
                except ElementTree.ParseError:
                    continue
                if index_root.tag.lower().endswith("sitemapindex"):
                    for sm_node in index_root.findall(".//sm:sitemap", _SITEMAP_NS):
                        if limit_reached:
                            break
                        loc_node = sm_node.find("sm:loc", _SITEMAP_NS)
                        if loc_node is None or loc_node.text is None:
                            continue
                        nested_url = loc_node.text.strip()
                        if nested_url in seen_sitemaps:
                            continue
                        seen_sitemaps.add(nested_url)
                        nested_response = await client.get(nested_url)
                        if nested_response.status_code >= 400:
                            continue
                        if len(nested_response.content) > max_sitemap_bytes:
                            continue
                        limit_reached = _append_entries(
                            collected,
                            _parse_sitemap_xml(nested_response.content, normalized_domain),
                            max_urls=max_urls,
                        )
                    continue
            limit_reached = _append_entries(collected, entries, max_urls=max_urls)

    if not collected:
        homepage = f"https://{normalized_domain}/"
        collected.append(SitemapEntry(url=homepage, lastmod=None))
    deduped: dict[str, SitemapEntry] = {}
    for entry in collected:
        deduped[entry.url] = entry
        if len(deduped) >= max_urls:
            break
    return list(deduped.values())
