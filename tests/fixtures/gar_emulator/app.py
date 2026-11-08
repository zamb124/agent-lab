"""Эмулятор DownloadService ФИАС и зеркала GAR-архивов для тестового стека.

Реальный ``GarImportService`` ходит по настоящему wire-протоколу:
``GetLastDownloadFileInfo``/``GetAllDownloadFileInfo`` отдают JSON с
``VersionId``/``GarXMLFullURL``/``GarXMLDeltaURL`` — URL указывают на этот
же сервис; ``/downloads/{version}/gar_{xml,delta}.zip`` собирает zip с
директорией ``77/`` и тремя XML-таблицами ГАР (ADDRESSOBJECTS, HOUSES,
ITEMS). Полная выгрузка — снимок на версию; дельта версии — только
изменившиеся строки плюс деактивации (``ISACTUAL=0``), поэтому контекст
имён дельта берёт из персистентного состояния импортёра.

Версии 98/99/100; дом 106 — демонстрация деактивации: активен в 98,
выведен в 100. Загрузка поддерживает HTTP Range (206), как
``fias-file.nalog.ru``.
"""

import io
import zipfile

from core.types import JsonObject
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import Response

_VERSIONS: Final = (98, 99, 100)
_LAST: Final = 100

# (OBJECTID, TYPENAME, NAME) — адресообразующие объекты региона 77.
_ADDR_OBJECTS: Final = (
    (1, "г.", "Москва"),
    (10, "ул.", "Тверская"),
    (11, "ул.", "Никольская"),
    (12, "ул.", "Арбат"),
    (13, "пл.", "Революции"),
    (14, "ул.", "Большая Садовая"),
)

# (OBJECTID, OBJECTGUID, HOUSENUM, parent OBJECTID) — дома; PATH в
# иерархии строится как «1.{parent}.{house}».
_HOUSES: Final = (
    (101, "11111111-1111-1111-1111-111111111101", "1", 10),
    (102, "22222222-2222-2222-2222-222222222102", "3", 10),
    (103, "33333333-3333-3333-3333-333333333103", "10", 11),
    (104, "44444444-4444-4444-4444-444444444104", "5", 12),
    (105, "55555555-5555-5555-5555-555555555105", "2", 13),
    (106, "66666666-6666-6666-6666-666666666106", "7", 14),
)

# Какие дома меняла каждая дельта-версия; в 100 дом 106 деактивирован.
_DELTA_HOUSES: Final = {98: (101, 106), 99: (102,), 100: (103, 104, 105)}
_DELTA_GONE: Final = {100: (106,)}
# В полной выгрузке дом 106 присутствует исторической строкой ISACTUAL=0.
_FULL_GONE: Final = (106,)

app = FastAPI(title="platform-gar-emulator")


def _addr_xml() -> str:
    rows = "".join(
        f'<OBJECT ID="{oid}" OBJECTID="{oid}" '
        + f'OBJECTGUID="00000000-0000-0000-0000-{oid:012d}" '
        + f'NAME="{name}" TYPENAME="{typename}" LEVEL="{level}" '
        + 'ISACTUAL="1" ISACTIVE="1"/>'
        for (oid, typename, name), level in zip(
            _ADDR_OBJECTS, (1, 8, 8, 8, 8, 8), strict=True
        )
    )
    return f"<ADDRESSOBJECTS>{rows}</ADDRESSOBJECTS>"


def _house_row(house: tuple[int, str, str, int], *, active: bool) -> str:
    object_id, guid, housenum, _parent = house
    flag = "1" if active else "0"
    return (
        f'<HOUSE ID="{object_id}" OBJECTID="{object_id}" '
        + f'OBJECTGUID="{guid}" HOUSENUM="{housenum}" '
        + f'ADDNUM1="" ADDNUM2="" ISACTUAL="{flag}" ISACTIVE="{flag}"/>'
    )


def _houses_xml(ids: tuple[int, ...], gone: tuple[int, ...]) -> str:
    by_id = {house[0]: house for house in _HOUSES}
    rows = "".join(_house_row(by_id[oid], active=True) for oid in ids)
    rows += "".join(_house_row(by_id[oid], active=False) for oid in gone)
    return f"<HOUSES>{rows}</HOUSES>"


def _hierarchy_xml(ids: tuple[int, ...]) -> str:
    by_id = {house[0]: house for house in _HOUSES}
    addr_rows = "".join(
        f'<ITEM ID="{oid}" OBJECTID="{oid}" PARENTOBJID="1" '
        + f'PATH="1.{oid}" ISACTIVE="1"/>'
        for oid, _t, _n in _ADDR_OBJECTS
        if oid != 1
    )
    house_rows = "".join(
        f'<ITEM ID="{oid}" OBJECTID="{oid}" PARENTOBJID="{by_id[oid][3]}" '
        + f'PATH="1.{by_id[oid][3]}.{oid}" ISACTIVE="1"/>'
        for oid in ids
    )
    return f"<ITEMS>{addr_rows}{house_rows}</ITEMS>"


def _zip_bytes(version: int, *, delta: bool) -> bytes:
    """Сборка архива региона 77: полная — снимок, дельта — изменения."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        if delta:
            house_ids = _DELTA_HOUSES.get(version, ())
            gone_ids = _DELTA_GONE.get(version, ())
            archive.writestr(
                f"77/AS_HOUSES_{version}_DELTA.XML",
                _houses_xml(house_ids, gone_ids),
            )
            archive.writestr(
                f"77/AS_ADM_HIERARCHY_{version}_DELTA.XML",
                _hierarchy_xml(house_ids),
            )
        else:
            all_ids = tuple(house[0] for house in _HOUSES if house[0] != 106)
            archive.writestr(
                f"77/AS_ADDR_OBJ_{version}_FULL.XML", _addr_xml()
            )
            archive.writestr(
                f"77/AS_HOUSES_{version}_FULL.XML",
                _houses_xml(all_ids, _FULL_GONE),
            )
            archive.writestr(
                f"77/AS_ADM_HIERARCHY_{version}_FULL.XML",
                _hierarchy_xml(all_ids),
            )
    return buf.getvalue()


def _file_info(request: Request, version: int) -> JsonObject:
    base = str(request.base_url).rstrip("/")
    return {
        "VersionId": version,
        "GarXMLFullURL": f"{base}/downloads/{version}/gar_xml.zip",
        "GarXMLDeltaURL": f"{base}/downloads/{version}/gar_delta.zip",
    }


@app.get("/WebServices/Public/GetLastDownloadFileInfo")
async def last_download_file_info(request: Request) -> JsonObject:
    return _file_info(request, _LAST)


@app.get("/WebServices/Public/GetAllDownloadFileInfo")
async def all_download_file_info(request: Request) -> list[JsonObject]:
    return [_file_info(request, version) for version in _VERSIONS]


@app.get("/downloads/{version}/gar_xml.zip")
async def full_archive(version: int, request: Request) -> Response:
    body = _zip_bytes(version, delta=False)
    return _archive_response(body, request)


@app.get("/downloads/{version}/gar_delta.zip")
async def delta_archive(version: int, request: Request) -> Response:
    body = _zip_bytes(version, delta=True)
    return _archive_response(body, request)


def _archive_response(body: bytes, request: Request) -> Response:
    """206 по ``Range: bytes=N-`` — resume-протокол fias-file.nalog.ru."""
    range_header = request.headers.get("range", "")
    if range_header.startswith("bytes="):
        start = int(range_header.removeprefix("bytes=").split("-")[0])
        if start > 0:
            return Response(
                content=body[start:],
                status_code=206,
                media_type="application/zip",
                headers={
                    "Content-Range": f"bytes {start}-{len(body) - 1}/{len(body)}",
                    "Content-Length": str(len(body) - start),
                },
            )
    return Response(
        content=body,
        media_type="application/zip",
        headers={"Content-Length": str(len(body))},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
