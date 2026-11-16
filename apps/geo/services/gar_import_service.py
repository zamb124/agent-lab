"""Импортёр ГАР/ФИАС: канонические имена и GUID поверх адресов OSM.

``gar_xml.zip`` разложен по директориям ``01``–``99`` (код региона) —
фильтрация именем члена архива, разбор потоковый (``iterparse`` в потоке,
память не зависит от размера выгрузки). Каноническое имя дома собирается из
материализованного ``PATH`` иерархии: цепочка «тип имя» + «д. N».

Bounded memory end-to-end: состояние региона — таблицы
``geo_gar_addr_objects``/``geo_gar_houses``, а не Python-коллекции и
``state_{region}.json``. Парсер-тред льёт строки батчами в очередь с
backpressure, консьюмер пишет их в Postgres; иерархия доливает ``path``
UPDATE FROM VALUES без ``house_ids`` в памяти. Матч читает дома
keyset-страницами ``object_id``, имена для PATH страницы подтягивает
одним запросом, результаты (enrich, живые колонки, очередь промахов)
сливаются чанками.

Дельта-архивы инкрементальны: PATH и имена живут в таблицах состояния,
дельта мержится upsert'ами. Курсор ``geo_source_cursors(source='gar')`` —
последний применённый VersionId; ``{v}:parsed`` — полный архив применён,
матч не завершён (резюме без повторного разбора); ``{v}:applying`` —
полный импорт оборван на записи (база частична — только повторная
полная выгрузка). Применение идемпотентно: перезапуск переигрывает
версию с нуля.

Матч к ``geo_addresses``: регион + нормализованный номер дома → схожесть
улицы (``NAME`` ⊆ street, иначе SequenceMatcher). Матч → upsert
``geo_address_enrich`` и живые колонки ``gar_guid``/``canonical_name`` —
админ-поля не трогаются; промах → ``geo_enrich_queue`` kind
``gar_unresolved`` (паркуется до появления резолвера). Снятие enrich —
``delete_stale_gar``: guid, не подтверждённый активным домом ни одного
региона, теряет и enrich-строку, и живые колонки.
"""

from __future__ import annotations

import asyncio
import queue
import re
import threading
import zipfile
from collections.abc import Callable, Iterator
from difflib import SequenceMatcher
from pathlib import Path
from typing import IO, ClassVar, NamedTuple, Protocol, TypeVar
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as _det
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from remotezip import RemoteZip

from apps.geo.config import GeoSettings
from apps.geo.db.import_lock import geo_import_lock
from apps.geo.models.geo_address import GeoAddress, GeoAddressMatchRow
from apps.geo.models.geo_address_enrich import GeoAddressEnrich
from apps.geo.models.geo_enrich_item import GeoEnrichItem
from apps.geo.models.geo_gar_addr_object import GeoGarAddrObject
from apps.geo.models.geo_gar_house import GarHouseRow, GeoGarHouse
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_source import GeoSource
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from apps.geo.services import address_match
from core.http import get_httpx_client
from core.http.client import SmartProxyClient
from core.imports import module_sdk
from core.logging import get_logger
from core.types import JsonObject

_SOURCE = "gar"
UNRESOLVED_KIND = "gar_unresolved"

# Только основные таблицы ``<TABLE>_<YYYYMMDD>_<uuid>.XML``: ``_PARAMS``/
# ``_DIVISION``-сородичи несут тот же OBJECTID без NAME/HOUSENUM/OBJECTGUID —
# их upsert затёр бы реальные поля пустыми (были: весь регион с пустыми
# именами/номерами домов). Цифра после ``_`` — дата версии, а не суффикс.
_MEMBER_RE_TEMPLATE = (
    r"(^|/){code}/(AS_ADDR_OBJ|AS_HOUSES|AS_ADM_HIERARCHY)_\d[^/]*\.XML$"
)

_logger = get_logger(__name__)


class _VersionInfo(BaseModel):
    """Одна запись ``DownloadFileInfo``: версия и URL выгрузок."""

    model_config: ClassVar[ConfigDict] = ConfigDict(populate_by_name=True)

    version_id: int = Field(alias="VersionId")
    full_url: str = Field(default="", alias="GarXMLFullURL")
    delta_url: str = Field(default="", alias="GarXMLDeltaURL")


class GarRegionSync(BaseModel):
    """Итог синка одного региона: режим, версии и счётчики матча."""

    status: str
    mode: str = ""
    version: int = 0
    versions: int = 0
    matched: int = 0
    unresolved: int = 0


class GarSyncResult(BaseModel):
    """Итог тика: ``skipped`` — причина пропуска, иначе итоги по регионам."""

    skipped: str = ""
    regions: dict[str, GarRegionSync] = {}


class _ApplyCounts(BaseModel):
    """Счётчики одного применённого архива."""

    houses: int = 0
    matched: int = 0
    unresolved: int = 0
    enqueued: int = 0


class _AddrChunk(NamedTuple):
    """Батч имён AS_ADDR_OBJ ``(object_id, name)``."""

    rows: list[tuple[int, str]]


class _HouseChunk(NamedTuple):
    """Батч активных домов AS_HOUSES."""

    rows: list[GarHouseRow]


class _GoneChunk(NamedTuple):
    """Батч OBJECTID выведенных из ФИАС домов."""

    rows: list[int]


class _HierChunk(NamedTuple):
    """Батч иерархии ``(object_id, PATH)``."""

    rows: list[tuple[int, str]]


class _StreamDone(NamedTuple):
    """Конец потока разбора."""


class _StreamError(NamedTuple):
    """Ошибка потока разбора — консьюмер пробрасывает."""

    error: BaseException


_Batch = (
    _AddrChunk | _HouseChunk | _GoneChunk | _HierChunk | _StreamDone | _StreamError
)


class _DefusedElementTree(Protocol):
    """Типизированная граница ``defusedxml.ElementTree`` (пакет без stub)."""

    def iterparse(
        self, source: IO[bytes], events: tuple[str, ...]
    ) -> Iterator[tuple[str, Element]]: ...


_DET = module_sdk(_det, _DefusedElementTree)


_ROOT_CLEAR_BATCH = 4096


def _iter_row_attrs(stream: IO[bytes]) -> Iterator[dict[str, str]]:
    """Строки XML-таблицы ГАР: каждый элемент с атрибутом ``OBJECTID``.

    ``element.clear()`` освобождает содержимое рядки, но пустой узел
    остаётся в списке детей корня — на десятках миллионов строк ГАР
    это гигабайты мёртвых объектов и OOMKill воркера. Корень (первый
    ``start``-элемент потока) очищается батчами: память парсера
    константна на файле любого размера.
    """
    iterator = _DET.iterparse(stream, events=("start", "end"))
    first = next(iterator, None)
    if first is None:
        return
    _event, root = first
    since_clear = 0
    for event, element in iterator:
        if event != "end":
            continue
        attrs = element.attrib
        if "OBJECTID" in attrs:
            yield dict(attrs)
        element.clear()
        since_clear += 1
        if since_clear >= _ROOT_CLEAR_BATCH:
            root.clear()
            since_clear = 0
    root.clear()


def _active(attrs: dict[str, str]) -> bool:
    """Актуальная действующая запись; отсутствие флага — «активна»."""
    return attrs.get("ISACTUAL", "1") == "1" and attrs.get("ISACTIVE", "1") == "1"


_STREAM_BATCH = 5000
_QUEUE_BATCHES = 8
_PUT_TIMEOUT_SECONDS = 0.5
_MATCH_PAGE = 5000
_PROGRESS_LOG_PAGES = 20

_RowT = TypeVar("_RowT")


def _push(
    out: queue.Queue[_Batch], item: _Batch, stop: threading.Event
) -> bool:
    """Батч в очередь с backpressure; ``False`` — консьюмер остановил поток."""
    while not stop.is_set():
        try:
            out.put(item, timeout=_PUT_TIMEOUT_SECONDS)
            return True
        except queue.Full:
            continue
    return False


def _stream_table(
    archive: zipfile.ZipFile,
    members: dict[str, str],
    kind: str,
    out: queue.Queue[_Batch],
    stop: threading.Event,
    row_of: Callable[[dict[str, str]], _RowT | None],
    chunk_of: Callable[[list[_RowT]], _Batch],
) -> bool:
    """Строки таблиц ``kind`` → батчи в очередь; ``False`` — останов."""
    for name, member_kind in members.items():
        if member_kind != kind or stop.is_set():
            continue
        batch: list[_RowT] = []
        with archive.open(name) as stream:
            for attrs in _iter_row_attrs(stream):
                row = row_of(attrs)
                if row is not None:
                    batch.append(row)
                if len(batch) >= _STREAM_BATCH:
                    if not _push(out, chunk_of(batch), stop):
                        return False
                    batch = []
        if batch and not _push(out, chunk_of(batch), stop):
            return False
    return True


def _addr_row(attrs: dict[str, str]) -> tuple[int, str] | None:
    """Активная строка AS_ADDR_OBJ → ``(object_id, "тип имя")``."""
    if not _active(attrs):
        return None
    name_part = attrs.get("NAME", "")
    type_part = attrs.get("TYPENAME", "")
    return int(attrs["OBJECTID"]), f"{type_part} {name_part}".strip()


def _hier_row(attrs: dict[str, str]) -> tuple[int, str]:
    """Строка AS_ADM_HIERARCHY → ``(object_id, PATH)``."""
    return int(attrs["OBJECTID"]), attrs.get("PATH", "")


def _stream_houses(
    archive: zipfile.ZipFile,
    members: dict[str, str],
    out: queue.Queue[_Batch],
    stop: threading.Event,
) -> bool:
    """AS_HOUSES: активные → ``_HouseChunk``, выведенные → ``_GoneChunk``."""
    houses: list[GarHouseRow] = []
    gone: list[int] = []
    for name, member_kind in members.items():
        if member_kind != "AS_HOUSES" or stop.is_set():
            continue
        with archive.open(name) as stream:
            for attrs in _iter_row_attrs(stream):
                object_id = int(attrs["OBJECTID"])
                if _active(attrs):
                    houses.append(
                        GarHouseRow(
                            object_id=object_id,
                            guid=attrs.get("OBJECTGUID", ""),
                            housenum=attrs.get("HOUSENUM", ""),
                            addnum1=attrs.get("ADDNUM1", ""),
                            addnum2=attrs.get("ADDNUM2", ""),
                        )
                    )
                    if len(houses) >= _STREAM_BATCH:
                        if not _push(out, _HouseChunk(rows=houses), stop):
                            return False
                        houses = []
                else:
                    gone.append(object_id)
                    if len(gone) >= _STREAM_BATCH:
                        if not _push(out, _GoneChunk(rows=gone), stop):
                            return False
                        gone = []
    if houses and not _push(out, _HouseChunk(rows=houses), stop):
        return False
    return not gone or _push(out, _GoneChunk(rows=gone), stop)


def _stream_zip(
    archive: zipfile.ZipFile,
    region_code: str,
    out: queue.Queue[_Batch],
    stop: threading.Event,
) -> None:
    """Таблицы директории региона → батчи: имена → дома → иерархия."""
    member_re = re.compile(
        _MEMBER_RE_TEMPLATE.format(code=re.escape(region_code)), re.IGNORECASE
    )
    members: dict[str, str] = {}
    for name in archive.namelist():
        match = member_re.match(name)
        if match is not None:
            members[name] = match.group(2)
    if not _stream_table(
        archive, members, "AS_ADDR_OBJ", out, stop, _addr_row, _AddrChunk
    ):
        return
    if not _stream_houses(archive, members, out, stop):
        return
    _ = _stream_table(
        archive, members, "AS_ADM_HIERARCHY", out, stop, _hier_row, _HierChunk
    )


def _stream_archive(
    url: str,
    region_code: str,
    *,
    timeout: float,
    out: queue.Queue[_Batch],
    stop: threading.Event,
) -> None:
    """Тред-производитель разбора: локальный zip либо HTTP Range.

    Полный ``gar_xml.zip`` (~54 GiB) на диск не скачивается — remotezip
    читает central directory и байтовые диапазоны членов региона. Конец
    потока и ошибка уходят в очередь — консьюмер никогда не висит на get.
    """
    try:
        if url.startswith("file://"):
            with zipfile.ZipFile(url.removeprefix("file://")) as archive:
                _stream_zip(archive, region_code, out, stop)
        else:
            with RemoteZip(url, timeout=timeout) as archive:
                _stream_zip(archive, region_code, out, stop)
    except Exception as exc:
        _ = _push(out, _StreamError(error=exc), stop)
        return
    _ = _push(out, _StreamDone(), stop)


_norm = address_match.norm
_street_norm = address_match.street_norm


def _canonical_name(
    addr_names: dict[int, str], path: str, house: GarHouseRow
) -> str:
    """«г. Москва, ул. Тверская, д. 1» из материализованного PATH."""
    parts: list[str] = []
    for raw_id in path.split("."):
        if raw_id == str(house.object_id):
            continue
        name = addr_names.get(int(raw_id)) if raw_id.isdigit() else None
        if name:
            parts.append(name)
    house_part = f"д. {house.housenum}" if house.housenum else ""
    if house.addnum1:
        house_part += f", к. {house.addnum1}"
    if house.addnum2:
        house_part += f", стр. {house.addnum2}"
    if house_part:
        parts.append(house_part)
    return ", ".join(parts)


class GarImportService:
    """Синк версий ФИАС → enrich-атрибуты адресов и очередь промахов."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def run_sync(self) -> GarSyncResult:
        """Тик: версии ФИАС → дельты или полная выгрузка → матч/промах."""
        if not self._settings.gar_sync_enabled:
            return GarSyncResult(skipped="gar_sync_disabled")
        source = await GeoSource.by_name(_SOURCE)
        if source is not None and not source.enabled:
            return GarSyncResult(skipped="source_disabled")
        if not self._settings.gar_region_codes:
            return GarSyncResult(skipped="no_regions")
        async with geo_import_lock(self._settings.database.geo_url) as acquired:
            if not acquired:
                return GarSyncResult(skipped="locked")
            await asyncio.to_thread(self._gc_work_dir)
            async with get_httpx_client(
                timeout=self._settings.gar_http_timeout_seconds
            ) as client:
                last = await self._fetch_version(
                    client, "GetLastDownloadFileInfo"
                )
                all_infos = await self._fetch_version_list(
                    client, "GetAllDownloadFileInfo"
                )
                regions: dict[str, GarRegionSync] = {}
                for region, code in self._settings.gar_region_codes.items():
                    regions[region] = await self._sync_region(
                        region=region,
                        code=code,
                        last=last,
                        infos=all_infos,
                    )
                if any(sync.status == "done" for sync in regions.values()):
                    generation = await GeoImportState.active_generation()
                    _ = await GeoAddressEnrich.delete_stale_gar()
                    _ = await GeoAddress.clear_stale_gar_attrs(
                        generation=generation
                    )
                return GarSyncResult(regions=regions)

    async def _fetch_version(
        self, client: SmartProxyClient, method: str
    ) -> _VersionInfo:
        """``GetLastDownloadFileInfo`` → последняя опубликованная версия."""
        response = await client.get(f"{self._settings.gar_info_url}/{method}")
        _ = response.raise_for_status()
        return _VersionInfo.model_validate_json(response.content)

    async def _fetch_version_list(
        self, client: SmartProxyClient, method: str
    ) -> list[_VersionInfo]:
        """``GetAllDownloadFileInfo`` → все опубликованные версии по возрастанию."""
        response = await client.get(f"{self._settings.gar_info_url}/{method}")
        _ = response.raise_for_status()
        infos = TypeAdapter(list[_VersionInfo]).validate_json(
            response.content
        )
        return sorted(infos, key=lambda info: info.version_id)

    async def _sync_region(
        self,
        *,
        region: str,
        code: str,
        last: _VersionInfo,
        infos: list[_VersionInfo],
    ) -> GarRegionSync:
        """План по курсору: резюме матча, дельта-цепочка или полная выгрузка."""
        cursor = await GeoSourceCursor.by_source_region(_SOURCE, region)
        raw = cursor.cursor if cursor is not None else ""
        done_version = int(raw) if raw.isdigit() else 0
        if (
            cursor is not None
            and cursor.status == GeoCursorStatus.DONE
            and done_version >= last.version_id
        ):
            return GarRegionSync(status="current", version=done_version)
        try:
            if raw == f"{last.version_id}:parsed" and (
                await GeoGarHouse.has_region_rows(region=region)
            ):
                counts = await self._match_and_apply(
                    region=region, version=last.version_id
                )
                await self._cursor_done(
                    region=region, version=last.version_id, matched=counts.matched
                )
                return GarRegionSync(
                    status="done",
                    mode="resume",
                    version=last.version_id,
                    matched=counts.matched,
                    unresolved=counts.unresolved,
                )
            pending = [info for info in infos if info.version_id > done_version]
            applying = raw.endswith(":applying") or raw.endswith(":parsed")
            chain_ok = (
                not applying
                and bool(pending)
                and pending[-1].version_id >= last.version_id
                and len(pending) <= self._settings.gar_max_delta_chain
                and all(info.delta_url for info in pending)
                and await GeoGarHouse.has_region_rows(region=region)
            )
            if chain_ok:
                matched = 0
                unresolved = 0
                for info in pending:
                    _ = await self._apply_archive(
                        url=info.delta_url,
                        region=region,
                        code=code,
                        version=info.version_id,
                        mode="delta",
                    )
                    counts = await self._match_and_apply(
                        region=region, version=info.version_id
                    )
                    matched += counts.matched
                    unresolved += counts.unresolved
                    _ = await GeoSourceCursor.upsert_progress(
                        source=_SOURCE,
                        region=region,
                        cursor=str(info.version_id),
                        rows_done=matched,
                        status=GeoCursorStatus.RUNNING,
                    )
                await self._cursor_done(
                    region=region,
                    version=pending[-1].version_id,
                    matched=matched,
                )
                return GarRegionSync(
                    status="done",
                    mode="delta",
                    versions=len(pending),
                    matched=matched,
                    unresolved=unresolved,
                )
            houses = await self._apply_archive(
                url=last.full_url,
                region=region,
                code=code,
                version=last.version_id,
                mode="full",
            )
            _ = await GeoSourceCursor.upsert_progress(
                source=_SOURCE,
                region=region,
                cursor=f"{last.version_id}:parsed",
                rows_done=houses,
                status=GeoCursorStatus.RUNNING,
            )
            counts = await self._match_and_apply(
                region=region, version=last.version_id
            )
            await self._cursor_done(
                region=region, version=last.version_id, matched=counts.matched
            )
            return GarRegionSync(
                status="done",
                mode="full",
                version=last.version_id,
                matched=counts.matched,
                unresolved=counts.unresolved,
            )
        except Exception as exc:
            await GeoSourceCursor.mark_failed(
                source=_SOURCE, region=region, error=f"{type(exc).__name__}: {exc}"
            )
            raise

    async def _cursor_done(
        self, *, region: str, version: int, matched: int
    ) -> None:
        """Курсор на применённую версию: тик завершён."""
        _ = await GeoSourceCursor.upsert_progress(
            source=_SOURCE,
            region=region,
            cursor=str(version),
            rows_done=matched,
            status=GeoCursorStatus.DONE,
        )

    async def _apply_archive(
        self,
        *,
        url: str,
        region: str,
        code: str,
        version: int,
        mode: str,
    ) -> int:
        """Стриминг-разбор архива → таблицы состояния; возвращает число домов."""
        if mode == "full":
            _ = await GeoGarHouse.delete_region(region=region)
            _ = await GeoGarAddrObject.delete_region(region=region)
            _ = await GeoSourceCursor.upsert_progress(
                source=_SOURCE,
                region=region,
                cursor=f"{version}:applying",
                rows_done=0,
                status=GeoCursorStatus.RUNNING,
            )
        out: queue.Queue[_Batch] = queue.Queue(maxsize=_QUEUE_BATCHES)
        stop = threading.Event()
        producer = asyncio.create_task(
            asyncio.to_thread(
                _stream_archive,
                url,
                code,
                timeout=self._settings.gar_http_timeout_seconds,
                out=out,
                stop=stop,
            )
        )
        houses = 0
        try:
            while True:
                batch = await asyncio.to_thread(out.get)
                if isinstance(batch, _StreamDone):
                    break
                if isinstance(batch, _StreamError):
                    raise batch.error
                if isinstance(batch, _AddrChunk):
                    _ = await GeoGarAddrObject.bulk_upsert_names(
                        region=region, rows=batch.rows
                    )
                elif isinstance(batch, _HouseChunk):
                    houses += len(batch.rows)
                    _ = await GeoGarHouse.bulk_upsert_active(
                        region=region, version=version, rows=batch.rows
                    )
                elif isinstance(batch, _GoneChunk):
                    if mode == "delta":
                        _ = await GeoGarHouse.bulk_deactivate(
                            region=region,
                            version=version,
                            object_ids=batch.rows,
                        )
                else:
                    _ = await GeoGarHouse.bulk_set_paths(
                        region=region, rows=batch.rows
                    )
            await producer
        except BaseException:
            stop.set()
            producer.add_done_callback(
                lambda task: None if task.cancelled() else task.exception()
            )
            raise
        return houses

    def _gc_work_dir(self) -> None:
        """Снос артефактов ``gar_work_dir`` после SIGKILL воркера (OOM/эвикт).

        ``gar_*.zip`` — недокачанные архивы старого пути загрузки;
        ``state_*.json`` — состояние до-табличной эпохи: таблицы его
        заменили, файлы мёртвым грузом лежали бы на PVC бессрочно.
        """
        work_dir = Path(self._settings.gar_work_dir)
        if not work_dir.is_dir():
            return
        for orphan in work_dir.glob("gar_*.zip"):
            orphan.unlink(missing_ok=True)
        for legacy in work_dir.glob("state_*.json"):
            legacy.unlink(missing_ok=True)

    async def _match_and_apply(
        self, *, region: str, version: int
    ) -> _ApplyCounts:
        """Матч домов архива к справочнику keyset-страницами → enrich/очередь."""
        generation = await GeoImportState.active_generation()
        candidates = await GeoAddress.list_for_enrich_match(
            region=region, generation=generation
        )
        by_num: dict[str, list[GeoAddressMatchRow]] = {}
        for row in candidates:
            by_num.setdefault(_norm(row.housenumber), []).append(row)
        houses = 0
        matched = 0
        unresolved_count = 0
        enqueued = 0
        written = 0
        last_object_id = 0
        pages = 0
        while True:
            page = await GeoGarHouse.match_page(
                region=region,
                version=version,
                last_object_id=last_object_id,
                limit=_MATCH_PAGE,
            )
            if not page:
                break
            pages += 1
            houses += len(page)
            last_object_id = page[-1].object_id
            name_ids = {
                int(raw_id)
                for house in page
                for raw_id in house.path.split(".")
                if raw_id.isdigit()
            }
            addr_names = await GeoGarAddrObject.names_for(
                region=region, object_ids=sorted(name_ids)
            )
            matched_rows: list[tuple[str, int, str, str]] = []
            unresolved: list[JsonObject] = []
            for house in page:
                canonical = _canonical_name(addr_names, house.path, house)
                street_name, path_names = self._street_of(
                    house.path, addr_names
                )
                hit = self._match_house(house, street_name, path_names, by_num)
                if hit is None:
                    unresolved.append(
                        {
                            "gar_objectid": str(house.object_id),
                            "gar_guid": house.guid,
                            "canonical_name": canonical,
                            "street": street_name,
                            "housenum": house.housenum,
                            "region": region,
                        }
                    )
                    continue
                matched_rows.append(
                    (hit.osm_type, hit.osm_id, house.guid, canonical)
                )
            matched += len(matched_rows)
            unresolved_count += len(unresolved)
            written += await GeoAddressEnrich.bulk_upsert(matched_rows)
            _ = await GeoAddress.bulk_set_gar_attrs(
                matched_rows, generation=generation
            )
            enqueued += await GeoEnrichItem.enqueue_missing(
                kind=UNRESOLVED_KIND,
                payloads=unresolved,
                dedupe_field="gar_objectid",
            )
            if pages % _PROGRESS_LOG_PAGES == 0:
                _logger.info(
                    "geo.gar.match_progress",
                    region=region,
                    version=version,
                    houses=houses,
                    matched=matched,
                    unresolved=unresolved_count,
                )
        await GeoStats.set_rows(
            generation=0,
            source=_SOURCE,
            region=region,
            entity="address_enrich",
            rows=written,
        )
        await GeoStats.set_rows(
            generation=0,
            source=_SOURCE,
            region=region,
            entity="unresolved",
            rows=unresolved_count,
        )
        _logger.info(
            "geo.gar.apply_done",
            region=region,
            version=version,
            houses=houses,
            matched=matched,
            unresolved=unresolved_count,
        )
        return _ApplyCounts(
            houses=houses,
            matched=matched,
            unresolved=unresolved_count,
            enqueued=enqueued,
        )

    @staticmethod
    def _street_of(
        path: str, addr_names: dict[int, str]
    ) -> tuple[str, set[str]]:
        """Имя улицы и нормализованные имена всей цепочки из PATH."""
        names = [
            addr_names[int(raw_id)]
            for raw_id in path.split(".")
            if raw_id.isdigit() and int(raw_id) in addr_names
        ]
        path_norm = {_norm(name) for name in names}
        street = names[-1] if names else ""
        return street, path_norm

    def _match_house(
        self,
        house: GarHouseRow,
        street_name: str,
        path_names: set[str],
        by_num: dict[str, list[GeoAddressMatchRow]],
    ) -> GeoAddressMatchRow | None:
        """Лучший кандидат по номеру дома + схожести улицы; ``None`` — промах."""
        variants = {_norm(house.housenum)}
        if house.addnum1:
            variants.add(_norm(f"{house.housenum}к{house.addnum1}"))
            variants.add(_norm(f"{house.housenum}{house.addnum1}"))
        if house.addnum2:
            variants.add(_norm(f"{house.housenum}стр{house.addnum2}"))
            variants.add(_norm(f"{house.housenum}{house.addnum2}"))
        best: GeoAddressMatchRow | None = None
        best_score = 0.0
        street_norm = _street_norm(street_name)
        for variant in variants:
            for candidate in by_num.get(variant, []):
                if candidate.city and not any(
                    part in _norm(candidate.city) or _norm(candidate.city) in part
                    for part in path_names
                ):
                    continue
                cand_street = _street_norm(candidate.street)
                score = (
                    1.0
                    if street_norm and street_norm in cand_street
                    else SequenceMatcher(None, street_norm, cand_street).ratio()
                )
                if score > best_score:
                    best = candidate
                    best_score = score
        if best is None or best_score < self._settings.gar_match_similarity:
            return None
        return best
