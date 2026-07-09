"""Structured SERP quality log events for Loki/Grafana."""

from __future__ import annotations

from core.logging import get_logger
from core.logging.attributes import (
    EVENT_SEARCH_SERP_CLICK,
    EVENT_SEARCH_SERP_SERVED,
    LOG_SEARCH_INDEX_ID,
    LOG_SERP_CACHE_KEY,
    LOG_SERP_CLICK_POSITION,
    LOG_SERP_CLICK_PROVIDER,
    LOG_SERP_CLICK_URL,
    LOG_SERP_MODE,
    LOG_SERP_PROVIDERS_SELECTED,
    LOG_SERP_QUERY,
    LOG_SERP_RESULTS_COUNT,
    LOG_SERP_TOTAL_COUNT,
)

logger = get_logger("platform.search")

_MAX_QUERY_LEN = 200
_MAX_URL_LEN = 512


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len]


def log_serp_served(
    *,
    query: str,
    mode: str,
    serp_cache_key: str,
    results_count: int,
    total_count: int,
    providers_selected: list[str],
) -> None:
    logger.info(
        EVENT_SEARCH_SERP_SERVED,
        **{
            LOG_SERP_QUERY: _truncate(query, _MAX_QUERY_LEN),
            LOG_SERP_MODE: mode,
            LOG_SERP_CACHE_KEY: serp_cache_key,
            LOG_SERP_RESULTS_COUNT: results_count,
            LOG_SERP_TOTAL_COUNT: total_count,
            LOG_SERP_PROVIDERS_SELECTED: ",".join(providers_selected),
        },
    )


def log_serp_click(
    *,
    serp_cache_key: str,
    query: str,
    mode: str,
    url: str,
    position: int,
    provider: str,
    search_index_id: str,
) -> None:
    logger.info(
        EVENT_SEARCH_SERP_CLICK,
        **{
            LOG_SERP_CACHE_KEY: serp_cache_key,
            LOG_SERP_QUERY: _truncate(query, _MAX_QUERY_LEN),
            LOG_SERP_MODE: mode,
            LOG_SERP_CLICK_URL: _truncate(url, _MAX_URL_LEN),
            LOG_SERP_CLICK_POSITION: position,
            LOG_SERP_CLICK_PROVIDER: provider,
            LOG_SEARCH_INDEX_ID: search_index_id,
        },
    )
