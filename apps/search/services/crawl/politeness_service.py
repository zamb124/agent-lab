"""Crawl politeness: robots.txt enforcement и per-domain rate limit."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx2

from apps.search.config import SearchCrawlConfig
from core.clients.redis_client import RedisClient
from core.http import get_httpx_client
from core.logging import get_logger

logger = get_logger(__name__)

ROBOTS_CACHE_KEY_PREFIX = "crawl:robots"
RATE_LIMIT_KEY_PREFIX = "crawl:fetch_slot"

# Отсутствие robots.txt (404 и т.п.) кэшируется отдельным маркером:
# пустая строка — валидный robots-контент "разрешено всё".
ROBOTS_ABSENT_SENTINEL = "__robots_absent__"

# Атомарная резервация слота fetch: читает время следующего свободного слота,
# сдвигает его на интервал и возвращает ожидание в миллисекундах.
_RESERVE_SLOT_LUA = """
local next_at = tonumber(redis.call('GET', KEYS[1]) or '0')
local now = tonumber(ARGV[1])
local interval = tonumber(ARGV[2])
local start = now
if next_at > now then
  start = next_at
end
redis.call('SET', KEYS[1], tostring(start + interval), 'PX', ARGV[3])
return start - now
"""


class CrawlPolitenessService:
    """
    Соблюдение правил источника перед fetch страницы.

    - robots.txt ``Disallow`` — запрещённые URL не скачиваются;
    - ``Crawl-delay`` (с потолком) либо дефолтный per-domain интервал —
      атомарный rate limit через Redis, ожидание слота в воркере.
    """

    def __init__(
        self,
        *,
        redis_client: RedisClient,
        crawl_config: SearchCrawlConfig,
    ) -> None:
        self._redis: RedisClient = redis_client
        self._crawl_config: SearchCrawlConfig = crawl_config

    async def is_url_allowed(self, url: str) -> bool:
        """Проверка ``Disallow`` robots.txt для канонического URL."""
        if not self._crawl_config.politeness_enabled:
            return True
        parser = await self._robots_parser(_url_host(url))
        if parser is None:
            return True
        return parser.can_fetch(self._crawl_config.robots_user_agent, url)

    async def wait_for_fetch_slot(self, url: str) -> float:
        """
        Резервирует слот fetch для домена и ждёт его наступления.

        Возвращает фактическое ожидание в секундах (для логов).
        """
        if not self._crawl_config.politeness_enabled:
            return 0.0
        host = _url_host(url)
        interval_seconds = await self._fetch_interval_seconds(host)
        if interval_seconds <= 0.0:
            return 0.0
        interval_ms = int(interval_seconds * 1000)
        ttl_ms = max(interval_ms * 10, 60_000)
        loop = asyncio.get_running_loop()
        now_ms = int(loop.time() * 1000)
        wait_raw = await self._redis.eval(
            _RESERVE_SLOT_LUA,
            1,
            f"{RATE_LIMIT_KEY_PREFIX}:{host}",
            now_ms,
            interval_ms,
            ttl_ms,
        )
        if not isinstance(wait_raw, (int, float)) or isinstance(wait_raw, bool):
            raise RuntimeError(f"crawl rate limit: unexpected redis eval reply: {wait_raw!r}")
        wait_seconds = max(0.0, float(wait_raw) / 1000.0)
        if wait_seconds > 0.0:
            await asyncio.sleep(wait_seconds)
        return wait_seconds

    async def _fetch_interval_seconds(self, host: str) -> float:
        interval = self._crawl_config.fetch_min_interval_seconds
        parser = await self._robots_parser(host)
        if parser is None:
            return interval
        crawl_delay = parser.crawl_delay(self._crawl_config.robots_user_agent)
        if crawl_delay is None:
            return interval
        return min(max(float(crawl_delay), interval), self._crawl_config.max_crawl_delay_seconds)

    async def _robots_parser(self, host: str) -> RobotFileParser | None:
        """Парсер robots.txt домена; None — правил нет (разрешено всё)."""
        robots_text = await self._robots_text(host)
        if robots_text is None:
            return None
        parser = RobotFileParser()
        parser.parse(robots_text.splitlines())
        return parser

    async def _robots_text(self, host: str) -> str | None:
        cache_key = f"{ROBOTS_CACHE_KEY_PREFIX}:{host}"
        cached = await self._redis.get(cache_key)
        if cached is not None:
            if cached == ROBOTS_ABSENT_SENTINEL:
                return None
            return cached
        robots_text = await self._download_robots_text(host)
        cache_value = robots_text if robots_text is not None else ROBOTS_ABSENT_SENTINEL
        _ = await self._redis.set(
            cache_key,
            cache_value,
            ttl=self._crawl_config.robots_cache_ttl_seconds,
        )
        return robots_text

    async def _download_robots_text(self, host: str) -> str | None:
        robots_url = f"https://{host}/robots.txt"
        try:
            async with get_httpx_client(
                timeout=self._crawl_config.http_timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(robots_url)
        except httpx2.HTTPError as exc:
            logger.warning(
                "crawl.robots_fetch_failed",
                crawl_domain=host,
                exception_type=type(exc).__name__,
                exception_message=str(exc),
            )
            return None
        if response.status_code != 200:
            return None
        return response.text


def _url_host(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if not host:
        raise ValueError(f"crawl politeness: url without host: {url}")
    return host
