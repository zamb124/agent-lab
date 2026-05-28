"""Адаптеры search providers."""

from apps.search.providers.base import SearchProvider
from apps.search.providers.linkup import LinkupSearchProvider, parse_linkup_results
from apps.search.providers.serper import SerperSearchProvider, parse_serper_results
from apps.search.providers.tavily import TavilySearchProvider, parse_tavily_results
from apps.search.providers.tinyfish import TinyFishSearchProvider, parse_tinyfish_results

__all__ = [
    "LinkupSearchProvider",
    "SearchProvider",
    "SerperSearchProvider",
    "TavilySearchProvider",
    "TinyFishSearchProvider",
    "parse_linkup_results",
    "parse_serper_results",
    "parse_tavily_results",
    "parse_tinyfish_results",
]
