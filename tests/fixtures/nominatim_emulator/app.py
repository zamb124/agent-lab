"""Эмулятор Nominatim ``/search`` для тестового стека.

Внешний API заменяется локальным сервером того же протокола (testing.mdc § Канон):
провайдер geocoding в стеке ходит сюда через ``GEOCODING__NOMINATIM_BASE_URL``.

Детерминизм:
- запрос ``"<lat>,<lng>"`` (две координаты через запятую) → точка с этими
  координатами — любая точка графа доступна тесту без правки эмулятора;
- пустой/неразобранный запрос → ``[]`` (маршрут «адрес не геокодится»).
"""

from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

app = FastAPI(title="platform-nominatim-emulator")


def _parse_point(q: str) -> tuple[float, float] | None:
    parts = [p.strip() for p in q.split(",")]
    if len(parts) != 2:
        return None
    try:
        lat, lng = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return lat, lng


@app.get("/search")
async def search(
    q: Annotated[str, Query()] = "",
    format: Annotated[str, Query()] = "jsonv2",  # noqa: A002 — имя параметра спеки Nominatim
    limit: Annotated[int, Query()] = 1,
) -> JSONResponse:
    _ = format, limit
    point = _parse_point(q)
    if point is None:
        return JSONResponse([])
    lat, lng = point
    return JSONResponse(
        [
            {
                "place_id": 1,
                "lat": str(lat),
                "lon": str(lng),
                "display_name": q,
                "importance": 0.5,
                "address": {"city": "Москва", "country": "Россия"},
            }
        ]
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
