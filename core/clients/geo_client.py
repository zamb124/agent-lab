"""
Типизированный клиент Geo API поверх ServiceClient (межсервисные вызовы).

Владелец гео-контракта — сервис ``geo``: продукты не дублируют SQL/зоны,
а ходят сюда за адресами в полигоне, подсказками, дорожными расстояниями,
матрицами, оптимальным порядком объезда и изохронами.
"""

from __future__ import annotations

from core.clients.geo_models import (
    GeoAddressListResult,
    GeoImportStatusResult,
    GeoIsochroneResult,
    GeoMatrixResult,
    GeoOrderResult,
    GeoRouteResult,
)
from core.clients.service_client import ServiceClient
from core.internal_context_headers import build_internal_context_headers
from core.types import JsonObject, require_json_object

GEO_API_V1_PREFIX = "/geo/api/v1"
# Runtime-идентичность сервисных вызовов без пользовательского контекста
# (витринные запросы анонима): middleware geo создаёт её при первом обращении.
GEO_CALLER_USER_ID = "platform.service.geo_client"


class GeoClient:
    """HTTP-клиент к сервису geo; контекст — из заголовков ServiceClient.

    ``company_id`` — для вызовов от имени компании без request-контекста
    (анонимные витрины): подписанные internal-заголовки заменяют контекст.
    """

    def __init__(
        self, http: ServiceClient | None = None, *, company_id: str | None = None
    ) -> None:
        self._http: ServiceClient = http or ServiceClient()
        self._headers: dict[str, str] | None = (
            build_internal_context_headers(
                company_id=company_id, user_id=GEO_CALLER_USER_ID
            )
            if company_id is not None
            else None
        )

    async def addresses_in_zone(
        self,
        *,
        zone: JsonObject,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> GeoAddressListResult:
        body: JsonObject = {"zone": zone, "limit": limit, "offset": offset}
        if q is not None:
            body["q"] = q
        return GeoAddressListResult.model_validate(
            require_json_object(
                await self._http.post(
                    "geo", f"{GEO_API_V1_PREFIX}/addresses/in-zone", json=body, headers=self._headers
                ),
                "geo addresses/in-zone response",
            )
        )

    async def suggest(
        self,
        *,
        q: str,
        zone: JsonObject | None = None,
        lat: float | None = None,
        lng: float | None = None,
        limit: int = 10,
    ) -> GeoAddressListResult:
        body: JsonObject = {"q": q, "limit": limit}
        if zone is not None:
            body["zone"] = zone
        if lat is not None and lng is not None:
            body["lat"] = lat
            body["lng"] = lng
        return GeoAddressListResult.model_validate(
            require_json_object(
                await self._http.post(
                    "geo", f"{GEO_API_V1_PREFIX}/addresses/suggest", json=body, headers=self._headers
                ),
                "geo addresses/suggest response",
            )
        )

    async def nearest(
        self, *, lat: float, lng: float, limit: int = 10
    ) -> GeoAddressListResult:
        return GeoAddressListResult.model_validate(
            require_json_object(
                await self._http.post(
                    "geo",
                    f"{GEO_API_V1_PREFIX}/addresses/nearest",
                    json={"lat": lat, "lng": lng, "limit": limit}, headers=self._headers,
                ),
                "geo addresses/nearest response",
            )
        )

    async def route_calculate(
        self,
        *,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float,
        mode: str = "car",
    ) -> GeoRouteResult:
        return GeoRouteResult.model_validate(
            require_json_object(
                await self._http.post(
                    "geo",
                    f"{GEO_API_V1_PREFIX}/route/calculate",
                    json={
                        "from_point": {"lat": from_lat, "lng": from_lng},
                        "to_point": {"lat": to_lat, "lng": to_lng},
                        "mode": mode,
                    },
                    headers=self._headers,
                    timeout=30.0,
                ),
                "geo route/calculate response",
            )
        )

    async def route_matrix(
        self,
        *,
        sources: list[tuple[float, float]],
        targets: list[tuple[float, float]],
        mode: str = "car",
    ) -> GeoMatrixResult:
        return GeoMatrixResult.model_validate(
            require_json_object(
                await self._http.post(
                    "geo",
                    f"{GEO_API_V1_PREFIX}/route/matrix",
                    json={
                        "sources": [{"lat": la, "lng": lo} for la, lo in sources],
                        "targets": [{"lat": la, "lng": lo} for la, lo in targets],
                        "mode": mode,
                    },
                    headers=self._headers,
                    timeout=60.0,
                ),
                "geo route/matrix response",
            )
        )

    async def route_optimal_order(
        self,
        *,
        start: tuple[float, float],
        points: list[tuple[float, float]],
        mode: str = "car",
        legs: bool = False,
    ) -> GeoOrderResult:
        return GeoOrderResult.model_validate(
            require_json_object(
                await self._http.post(
                    "geo",
                    f"{GEO_API_V1_PREFIX}/route/optimal-order",
                    json={
                        "start": {"lat": start[0], "lng": start[1]},
                        "points": [{"lat": la, "lng": lo} for la, lo in points],
                        "mode": mode,
                        "legs": legs,
                    },
                    headers=self._headers,
                    timeout=60.0,
                ),
                "geo route/optimal-order response",
            )
        )

    async def route_isochrone(
        self, *, lat: float, lng: float, minutes: float, mode: str = "car"
    ) -> GeoIsochroneResult:
        return GeoIsochroneResult.model_validate(
            require_json_object(
                await self._http.post(
                    "geo",
                    f"{GEO_API_V1_PREFIX}/route/isochrone",
                    json={
                        "center": {"lat": lat, "lng": lng},
                        "minutes": minutes,
                        "mode": mode,
                    },
                    headers=self._headers,
                    timeout=60.0,
                ),
                "geo route/isochrone response",
            )
        )

    async def import_status(self) -> GeoImportStatusResult:
        return GeoImportStatusResult.model_validate(
            require_json_object(
                await self._http.get(
                    "geo", f"{GEO_API_V1_PREFIX}/import/status", headers=self._headers
                ),
                "geo import/status response",
            )
        )
