"""Эмулятор apidata.mos.ru для тестового стека.

Контракт — как у реального Портала открытых данных Москвы:

- ``GET /v1/datasets/{id}/rows?$top=&$skip=&api_key=`` →
  ``{Count, Rows: [{Id, Number, Cells: {...}}]}``; неверный/пустой
  ``api_key`` → 401.
- Пагинация ``$skip``/$top — датасет режется на страницы, resume идёт по
  смещению (как прод: Count — всего строк, Rows — окно).

Датасет ``60562`` (адресный реестр) — детерминированные строки с
``Cells.ADDRESS``/``UNOM``/``geoData``; пустой датасет ``empty`` —
``Rows: []``.
"""

from __future__ import annotations

from typing import Final

from core.types import JsonObject
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

_API_KEY: Final = "test-datamos-key"

app = FastAPI(title="platform-datamos-emulator")


def _row(row_id: int, address: str, unom: str, lng: float, lat: float) -> JsonObject:
    return {
        "Id": row_id,
        "Number": row_id,
        "Cells": {
            "ADDRESS": address,
            "UNOM": unom,
            "geoData": {"type": "Point", "coordinates": [lng, lat]},
        },
    }


_DATASETS: Final = {
    "60562": [
        _row(1, "г. Москва, ул. Тверская, д. 1", "1", 37.6120, 55.7600),
        _row(2, "г. Москва, ул. Тверская, д. 3", "2", 37.6130, 55.7610),
        _row(3, "г. Москва, ул. Никольская, д. 10", "3", 37.6210, 55.7540),
        _row(4, "г. Москва, ул. Арбат, д. 5", "4", 37.5960, 55.7500),
        _row(5, "г. Москва, пл. Революции, д. 2", "5", 37.6220, 55.7570),
    ],
    "empty": [],
}


@app.get("/v1/datasets/{dataset_id}/rows")
async def dataset_rows(
    dataset_id: str,
    api_key: str = "",
    top: int = Query(default=500, alias="$top"),
    skip: int = Query(default=0, alias="$skip"),
) -> JSONResponse:
    if api_key != _API_KEY:
        return JSONResponse(status_code=401, content={"message": "Unauthorized"})
    rows = _DATASETS.get(dataset_id, [])
    window = rows[skip : skip + top]
    return JSONResponse(content={"Count": len(rows), "Rows": window})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
