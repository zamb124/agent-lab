"""Эмулятор публичного API НСПД/ЕГРН для тестового стека.

Контракт — как у реального ``nspd.gov.ru`` (см. ``NspdClient``):

- ``POST /api/geoportal/v1/intersects?typeIntersect=fullObject`` —
  GeoJSON FeatureCollection объектов категории внутри полигона ``geom``.
- ``GET /api/geoportal/v2/search/geoportal?query=&layersId=`` — поисковая
  выдача ``{data: FeatureCollection, meta: [...]}``; пусто → 404.
- Запрос без заголовка ``Referer: …nspd.gov.ru/map…`` → 403, как у прода.
- ``query`` с префиксом ``flaky:`` — первый запрос отвечает 500, следующий
  отдаёт данные (проверка retry/backoff клиента).

Здания — детерминированный набор точек внутри тестового региона
``nspd_e2e`` (bbox 55.745–55.765 × 37.59–37.63): контур — ромб 40 м
вокруг центроида, атрибуты в ``properties.options`` — как у прода.
"""

from __future__ import annotations

import re
from typing import Final, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.types import JsonObject

_LAYER_ID: Final = 36049
_REFERER_RE: Final = re.compile(r"nspd\.gov\.ru")

# (cad_num, address, floors, lng, lat) — центроиды тестовых зданий.
_BUILDINGS: Final = (
    ("77:01:0001001:1", "г Москва, ул Тверская, д 1", 9, 37.6120, 55.7600),
    ("77:01:0001001:2", "г Москва, ул Никольская, д 10", 5, 37.6210, 55.7540),
    ("77:01:0001001:3", "г Москва, пл Революции, д 2", 3, 37.6220, 55.7570),
    ("77:01:0001001:4", "г Москва, ул Арбат, д 5", 7, 37.5960, 55.7500),
)

# Префикс запроса, который один раз отвечает 500 (проверка retry).
_FLAKY_PREFIX: Final = "flaky:"

app = FastAPI(title="platform-nspd-emulator")

_flaky_hits: dict[str, int] = {}


def _polygon(lng: float, lat: float) -> JsonObject:
    """Ромб ~40 м вокруг центроида — контур здания."""
    half = 0.00018
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lng - half, lat],
                [lng, lat - half],
                [lng + half, lat],
                [lng, lat + half],
                [lng - half, lat],
            ]
        ],
    }


def _feature(building: tuple[str, str, int, float, float]) -> dict[str, object]:
    cad_num, address, floors, lng, lat = building
    return {
        "type": "Feature",
        "properties": {
            "category": _LAYER_ID,
            "options": {
                "cad_num": cad_num,
                "address": address,
                "floors": floors,
                "interaction_type": "feature",
            },
        },
        "geometry": _polygon(lng, lat),
    }


def _norm(value: str) -> str:
    """Нормализация адресной строки: lowercase, без знаков препинания."""
    return re.sub(r"[^0-9a-zа-яё]+", " ", value.lower()).strip()


def _in_polygon(lng: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-casting: центроид здания внутри ячейки-полигона."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (
            yj - yi
        ) + xi:
            inside = not inside
        j = i
    return inside


def _check_referer(request: Request) -> JSONResponse | None:
    referer = request.headers.get("referer", "")
    if not _REFERER_RE.search(referer):
        return JSONResponse(
            status_code=403,
            content={"code": 403, "message": "Forbidden", "requestId": "emu"},
        )
    return None


@app.get("/api/geoportal/v2/search/geoportal")
async def search_geoportal(request: Request, query: str = "") -> JSONResponse:
    denied = _check_referer(request)
    if denied is not None:
        return denied
    if query.startswith(_FLAKY_PREFIX):
        hits = _flaky_hits.get(query, 0)
        _flaky_hits[query] = hits + 1
        query = query[len(_FLAKY_PREFIX):]
        if hits == 0:
            return JSONResponse(
                status_code=500,
                content={"code": 500, "message": "flaky", "requestId": "emu"},
            )
    norm_query = _norm(query)
    matches = [
        _feature(b)
        for b in _BUILDINGS
        if b[0].startswith(query) or norm_query in _norm(b[1])
    ]
    if not matches:
        return JSONResponse(status_code=404, content={})
    return JSONResponse(
        content={
            "data": {"type": "FeatureCollection", "features": matches},
            "meta": [{"totalCount": len(matches), "categoryId": _LAYER_ID}],
        }
    )


@app.post("/api/geoportal/v1/intersects")
async def intersects(request: Request) -> JSONResponse:
    denied = _check_referer(request)
    if denied is not None:
        return denied
    body = cast(JsonObject, await request.json())
    geom = body.get("geom")
    features_in = (
        cast(list[JsonObject], geom.get("features", []))
        if isinstance(geom, dict)
        else []
    )
    ring: list[list[float]] = []
    if features_in:
        first = features_in[0]
        geometry_raw = first.get("geometry")
        geometry = geometry_raw if isinstance(geometry_raw, dict) else {}
        coords = cast(list[object], geometry.get("coordinates", []))
        if coords and isinstance(coords[0], list):
            ring = cast(list[list[float]], coords[0])
    matches = [
        _feature(b)
        for b in _BUILDINGS
        if ring and _in_polygon(b[3], b[4], ring)
    ]
    return JSONResponse(
        content={"type": "FeatureCollection", "features": matches}
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
