"""Геометрия зон доставки: GeoJSON-полигоны и point-in-polygon.

Зона хранится как GeoJSON Polygon: {"type":"Polygon","coordinates":[[[lng,lat],...]]}
(внешнее кольцо в coordinates[0], GeoJSON-порядок долгота/широта).
"""

from __future__ import annotations

from core.types import JsonObject


def polygon_ring(zone: JsonObject | None) -> list[tuple[float, float]] | None:
    """Внешнее кольцо полигона зоны как [(lng, lat)] или None если зоны нет."""
    if not zone or zone.get("type") != "Polygon":
        return None
    coords = zone.get("coordinates")
    if (
        not isinstance(coords, list)
        or not coords
        or not isinstance(coords[0], list)
        or len(coords[0]) < 4  # замкнутое кольцо минимум 4 точки
    ):
        return None
    ring: list[tuple[float, float]] = []
    for pt in coords[0]:
        if (
            isinstance(pt, (list, tuple))
            and len(pt) >= 2
            and isinstance(pt[0], (int, float, str))
            and isinstance(pt[1], (int, float, str))
            and not isinstance(pt[0], bool)
            and not isinstance(pt[1], bool)
        ):
            try:
                ring.append((float(pt[0]), float(pt[1])))
            except (TypeError, ValueError):
                return None
        else:
            return None
    return ring if len(ring) >= 4 else None


def point_in_polygon(lng: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """Ray casting: точка (lng,lat) внутри кольца [(lng,lat)].

    Точки строго на границе считаются внутренними (помилосердствуем к граничным
    адресам — зона рисуется директором с запасом).
    """
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        # точка на отрезке границы
        cross = (lat - yi) * (xj - xi) - (lng - xi) * (yj - yi)
        if abs(cross) < 1e-9 and min(xi, xj) - 1e-9 <= lng <= max(xi, xj) + 1e-9 and min(yi, yj) - 1e-9 <= lat <= max(yi, yj) + 1e-9:
            return True
        if (yi > lat) != (yj > lat):
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < x_intersect:
                inside = not inside
        j = i
    return inside


def zone_covers_point(zone: JsonObject | None, lat: float, lng: float) -> bool | None:
    """Зона покрывает точку? None — зоны нет/невалидна (ограничения не применяется)."""
    ring = polygon_ring(zone)
    if ring is None:
        return None
    return point_in_polygon(lng, lat, ring)


def bbox_of_ring(ring: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """(min_lng, min_lat, max_lng, max_lat) кольца — для фита карты."""
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


_ZONE_MAX_POINTS = 256


def is_valid_delivery_zone(zone: JsonObject | None) -> bool:
    """Строгая валидация зоны на запись: один внешний ring GeoJSON Polygon.

    Поддерживаем ровно то, что умеет point-in-polygon: type=="Polygon",
    одно кольцо (дырки и MultiPolygon отклоняем честно), 4..256 точек,
    каждая — числовая пара [lng±180, lat±90], кольцо замкнуто.
    Пустая зона ({}/None) — валидна: так зону снимают.
    """
    if not zone:
        return True
    if zone.get("type") != "Polygon":
        return False
    coords = zone.get("coordinates")
    if (
        not isinstance(coords, list)
        or len(coords) != 1  # только внешнее кольцо — дырок/MultiPolygon нет
        or not isinstance(coords[0], list)
    ):
        return False
    ring_raw = coords[0]
    if not 4 <= len(ring_raw) <= _ZONE_MAX_POINTS:
        return False
    first = last = None
    for pt in ring_raw:
        if (
            not isinstance(pt, (list, tuple))
            or len(pt) != 2
            or isinstance(pt[0], bool)
            or isinstance(pt[1], bool)
            or not isinstance(pt[0], (int, float))
            or not isinstance(pt[1], (int, float))
        ):
            return False
        lng, lat = float(pt[0]), float(pt[1])
        if not (-180.0 <= lng <= 180.0 and -90.0 <= lat <= 90.0):
            return False
        if first is None:
            first = (lng, lat)
        last = (lng, lat)
    if first is None or last is None:
        return False
    return abs(first[0] - last[0]) < 1e-9 and abs(first[1] - last[1]) < 1e-9
