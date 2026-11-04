"""Nominatim-геокодер (openstreetmap.org или self-hosted).

Политика OSM: ≤1 rps, обязательный User-Agent — у нас объём на чекауте + кэш.
Redis-кэш `geo:q:{sha256(norm)}` TTL из конфига — повторные адреса не бьют API.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import ClassVar
from typing import cast as type_cast

from core.clients.geocoding.base import GeocodedAddress
from core.clients.redis_client import RedisClient
from core.config.models import GeocodingConfig
from core.errors.boundary import PlatformUnavailableError
from core.http.client import request_public_oauth
from core.logging import get_logger
from core.types import JsonValue, require_json_array

log = get_logger(__name__)


def _cache_key(query: str) -> str:
    norm = " ".join(query.strip().lower().split())
    return f"geo:q:{hashlib.sha256(norm.encode()).hexdigest()[:32]}"


def _scalar(value: JsonValue | None) -> str | int | float | None:
    return value if isinstance(value, (str, int, float)) and not isinstance(value, bool) else None


def _parse_item(item: Mapping[str, JsonValue], fallback_name: str) -> GeocodedAddress | None:
    lat_v, lon_v = _scalar(item.get("lat")), _scalar(item.get("lon"))
    if lat_v is None or lon_v is None:
        return None
    address_raw = item.get("address")
    address: Mapping[str, JsonValue] = (
        address_raw if isinstance(address_raw, dict) else {}
    )
    city = next(
        (
            v
            for k in ("city", "town", "village", "municipality")
            if (v := _scalar(address.get(k))) is not None and str(v)
        ),
        "",
    )
    importance = _scalar(item.get("importance"))
    display = _scalar(item.get("display_name"))
    country = _scalar(address.get("country"))
    return GeocodedAddress(
        lat=float(lat_v),
        lng=float(lon_v),
        normalized_address=str(display) if display else fallback_name,
        confidence=float(importance) if importance is not None else 0.0,
        city=str(city),
        country=str(country) if country else "",
    )


class NominatimGeocoder:
    """Геокодинг через Nominatim /search с Redis-кэшем."""

    _MISSING: ClassVar[str] = "__none__"

    def __init__(self, config: GeocodingConfig, redis: RedisClient) -> None:
        self._cfg: GeocodingConfig = config
        self._redis: RedisClient = redis

    async def geocode(self, query: str) -> GeocodedAddress | None:
        """Нормализовать адрес и вернуть координаты; None — не нашёл/недоступен."""
        query = query.strip()
        if not query or not self._cfg.enabled:
            return None
        key = _cache_key(query)
        cached = await self._redis.get(key)
        if cached is not None:
            if cached == self._MISSING:
                return None
            return GeocodedAddress.model_validate_json(cached)

        try:
            resp = await request_public_oauth(
                "GET",
                f"{self._cfg.nominatim_base_url.rstrip('/')}/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 1,
                    "accept-language": "ru",
                    "addressdetails": 1,
                },
                headers={
                    "User-Agent": self._cfg.user_agent,
                    "Accept-Language": "ru",
                },
                timeout=self._cfg.timeout_seconds,
            )
            _ = resp.raise_for_status()
            data = require_json_array(type_cast(JsonValue, resp.json()))
        except Exception as exc:
            log.warning("nominatim.geocode.failed", query=query, error=str(exc))
            raise PlatformUnavailableError(
                f"Geocoding upstream failed: {exc}"
            ) from exc

        result: GeocodedAddress | None = None
        if data:
            item = data[0]
            if isinstance(item, dict):
                result = _parse_item(item, query)

        ttl = self._cfg.cache_ttl_seconds
        if result is not None:
            _ = await self._redis.set(key, result.model_dump_json(), ttl=ttl)
        else:
            # miss-кэш короче — чтобы временная пустота не сидела месяц
            _ = await self._redis.set(key, self._MISSING, ttl=min(ttl, 3600))
        return result
