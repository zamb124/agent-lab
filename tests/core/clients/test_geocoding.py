"""Nominatim-геокодер: эмуляция провайдера на границе HTTP + Redis-кэш.

Эмулятор — реальный HTTP-ответ провайдерной формы через MockTransport
(install_mock_httpx_client): геокодер ходит в «сеть» как в проде, а
контракт ответа повторяет nominatim.openstreetmap.org/search.
"""

from __future__ import annotations

import httpx2
import pytest

from apps.flows.config import get_settings
from core.clients.geocoding.nominatim import NominatimGeocoder
from core.clients.redis_client import RedisClient
from core.config.models import GeocodingConfig
from core.errors.boundary import PlatformUnavailableError
from core.utils.geo import bbox_of_ring, point_in_polygon, polygon_ring, zone_covers_point
from tests.core.http_proxy_helpers import install_mock_httpx_client


@pytest.fixture
async def redis_client() -> RedisClient:
    client = RedisClient(get_settings().database.redis_url)
    await client.connect()
    yield client
    await client.close()


def _nominatim_handler(calls: list[httpx2.Request], body: object, status: int = 200):
    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(status, json=body, request=request)

    return handler


_MOSCOW_ITEM = [
    {
        "place_id": 12345,
        "lat": "55.755826",
        "lon": "37.617300",
        "display_name": "Тверская улица, 1, Москва, Россия",
        "importance": 0.71,
        "address": {"city": "Москва", "country": "Россия"},
    }
]


class TestNominatimGeocoder:
    async def test_parses_provider_response(
        self, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, unique_id: str
    ) -> None:
        calls: list[httpx2.Request] = []
        install_mock_httpx_client(
            monkeypatch, _nominatim_handler(calls, _MOSCOW_ITEM)
        )
        geo = NominatimGeocoder(GeocodingConfig(enabled=True), redis_client)

        addr = await geo.geocode(f"Москва, Тверская 1 {unique_id}")

        assert addr is not None
        assert addr.lat == pytest.approx(55.755826)
        assert addr.lng == pytest.approx(37.6173)
        assert addr.normalized_address == "Тверская улица, 1, Москва, Россия"
        assert addr.city == "Москва"
        assert addr.country == "Россия"
        assert len(calls) == 1
        request = calls[0]
        assert request.url.params["format"] == "jsonv2"
        assert request.url.params["limit"] == "1"
        assert "nominatim.openstreetmap.org" in str(request.url)

    async def test_empty_result_returns_none_and_caches_miss(
        self, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, unique_id: str
    ) -> None:
        calls: list[httpx2.Request] = []
        install_mock_httpx_client(monkeypatch, _nominatim_handler(calls, []))
        geo = NominatimGeocoder(GeocodingConfig(enabled=True), redis_client)
        query = f"Несуществующая улица {unique_id}"

        assert await geo.geocode(query) is None
        assert await geo.geocode(query) is None
        assert len(calls) == 1  # miss-кэш: второй раз в провайдер не ходим

    async def test_hit_cached_without_http(
        self, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, unique_id: str
    ) -> None:
        calls: list[httpx2.Request] = []
        install_mock_httpx_client(
            monkeypatch, _nominatim_handler(calls, _MOSCOW_ITEM)
        )
        geo = NominatimGeocoder(GeocodingConfig(enabled=True), redis_client)
        query = f"Москва, Тверская 1 {unique_id}"

        first = await geo.geocode(query)
        second = await geo.geocode(f"  {query.upper()}  ")
        assert first is not None and second is not None
        assert second.lat == first.lat
        # кэш-ключ нормализован: регистр/пробелы не бьют провайдера повторно
        assert len(calls) == 1

    async def test_upstream_error_raises_unavailable(
        self, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, unique_id: str
    ) -> None:
        calls: list[httpx2.Request] = []
        install_mock_httpx_client(
            monkeypatch, _nominatim_handler(calls, {"error": "boom"}, status=500)
        )
        geo = NominatimGeocoder(GeocodingConfig(enabled=True), redis_client)

        with pytest.raises(PlatformUnavailableError):
            await geo.geocode(f"Москва {unique_id}")

    async def test_disabled_returns_none(
        self, redis_client: RedisClient, unique_id: str
    ) -> None:
        geo = NominatimGeocoder(GeocodingConfig(enabled=False), redis_client)
        assert await geo.geocode(f"Москва {unique_id}") is None

    async def test_blank_query_returns_none(
        self, redis_client: RedisClient
    ) -> None:
        geo = NominatimGeocoder(GeocodingConfig(enabled=True), redis_client)
        assert await geo.geocode("   ") is None


_SQUARE_RING = [(37.55, 55.70), (37.75, 55.70), (37.75, 55.80), (37.55, 55.80), (37.55, 55.70)]


class TestGeoUtils:
    """Геометрия зон: ray casting, парсинг GeoJSON-кольца, покрытие точки."""

    def test_point_inside_and_outside(self) -> None:
        assert point_in_polygon(37.62, 55.75, _SQUARE_RING) is True
        assert point_in_polygon(37.20, 55.50, _SQUARE_RING) is False
        assert point_in_polygon(37.76, 55.75, _SQUARE_RING) is False

    def test_point_on_boundary_is_inside(self) -> None:
        # точка строго на грани квадрата — «помилосердствована» внутрь
        assert point_in_polygon(37.55, 55.75, _SQUARE_RING) is True
        assert point_in_polygon(37.65, 55.80, _SQUARE_RING) is True

    def test_concave_polygon(self) -> None:
        # Г-образная зона: вырез справа-сверху
        ring = [
            (0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0),
            (2.0, 4.0), (0.0, 4.0), (0.0, 0.0),
        ]
        assert point_in_polygon(1.0, 1.0, ring) is True   # в основном теле
        assert point_in_polygon(3.0, 3.0, ring) is False  # в вырезе
        assert point_in_polygon(3.0, 1.0, ring) is True   # в нижнем плече

    def test_polygon_ring_parsing(self) -> None:
        assert polygon_ring(None) is None
        assert polygon_ring({}) is None
        assert polygon_ring({"type": "Point", "coordinates": [1, 2]}) is None
        assert polygon_ring({"type": "Polygon", "coordinates": []}) is None
        assert polygon_ring(
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1]]]}
        ) is None  # незамкнутое кольцо < 4 точек
        ring = polygon_ring(
            {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
        )
        assert ring == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 0.0)]

    def test_zone_covers_point_semantics(self) -> None:
        zone = {"type": "Polygon", "coordinates": [[list(p) for p in _SQUARE_RING]]}
        assert zone_covers_point(None, 55.75, 37.62) is None
        assert zone_covers_point({}, 55.75, 37.62) is None
        assert zone_covers_point(zone, 55.75, 37.62) is True
        assert zone_covers_point(zone, 55.50, 37.20) is False

    def test_bbox(self) -> None:
        assert bbox_of_ring(_SQUARE_RING) == (37.55, 55.70, 37.75, 55.80)
