"""Импортёр ГАР/ФИАС: канонические имена и GUID поверх адресов OSM.

``gar_xml.zip`` разложен по директориям ``01``–``99`` (код региона) —
фильтрация именем члена архива, разбор потоковый (``iterparse`` в потоке,
память не зависит от размера выгрузки). Каноническое имя дома собирается из
материализованного ``PATH`` иерархии: цепочка «тип имя» + «д. N».

Матч к ``geo_addresses``: регион + нормализованный номер дома → схожесть
улицы (``NAME`` ⊆ street, иначе SequenceMatcher). Матч → upsert
``geo_address_enrich`` и живые колонки ``gar_guid``/``canonical_name`` —
админ-поля не трогаются; промах → ``geo_enrich_queue`` kind
``gar_unresolved`` (паркуется до появления резолвера).

Дельта-архивы инкрементальны: PATH дома разрешается через персистентное
состояние ``state_{region}.json`` в ``gar_work_dir`` (addr-имена, дома,
иерархия), дельта мержится в него. Курсор без файла состояния → полная
выгрузка: контекст цепочки восстановить неоткуда.

Курсор ``geo_source_cursors(source='gar')`` — последний применённый
VersionId. Свежее → цепочка дельт ``GetAllDownloadFileInfo``; цепочка
длиннее ``gar_max_delta_chain``, курсора нет или state-файл потерян →
полная выгрузка. Применение идемпотентно: перезапуск переигрывает версию
с нуля.
"""

from __future__ import annotations

import asyncio
import re
import zipfile
from collections.abc import Iterator
from difflib import SequenceMatcher
from pathlib import Path
from typing import IO, ClassVar, Protocol
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as _det
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from apps.geo.config import GeoSettings
from apps.geo.db.import_lock import geo_import_lock
from apps.geo.models.geo_address import GeoAddress
from apps.geo.models.geo_address_enrich import GeoAddressEnrich
from apps.geo.models.geo_enrich_item import GeoEnrichItem
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

_MEMBER_RE_TEMPLATE = r"(^|/){code}/(AS_ADDR_OBJ|AS_HOUSES|AS_ADM_HIERARCHY)_[^/]*\.XML$"

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


class _HouseRow(BaseModel):
    """Дом из ``AS_HOUSES``: стабильный ключ — ``OBJECTID``."""

    object_id: int
    guid: str
    housenum: str
    addnum1: str
    addnum2: str


class _ParsedArchive(BaseModel):
    """Результат разбора архива одного региона.

    ``houses`` — активные дома этого архива (область матча); ``gone_houses``
    — деактивированные OBJECTID для чистки состояния; ``addr_names`` и
    ``paths`` — строки адресных объектов и иерархии этого архива.
    """

    addr_names: dict[int, str]
    houses: list[_HouseRow]
    paths: dict[int, str]
    gone_houses: list[int]


class _GarState(BaseModel):
    """Персистентное состояние региона: контекст для инкрементальных дельт."""

    addr_names: dict[int, str] = {}
    houses: dict[int, _HouseRow] = {}
    paths: dict[int, str] = {}


class _DefusedElementTree(Protocol):
    """Типизированная граница ``defusedxml.ElementTree`` (пакет без stub)."""

    def iterparse(
        self, source: IO[bytes], events: tuple[str, ...]
    ) -> Iterator[tuple[str, Element]]: ...


_DET = module_sdk(_det, _DefusedElementTree)


def _iter_row_attrs(stream: IO[bytes]) -> Iterator[dict[str, str]]:
    """Строки XML-таблицы ГАР: каждый элемент с атрибутом ``OBJECTID``."""
    for _event, element in _DET.iterparse(stream, events=("end",)):
        attrs = element.attrib
        if "OBJECTID" in attrs:
            yield dict(attrs)
        element.clear()


def _active(attrs: dict[str, str]) -> bool:
    """Актуальная действующая запись; отсутствие флага — «активна»."""
    return attrs.get("ISACTUAL", "1") == "1" and attrs.get("ISACTIVE", "1") == "1"


def _parse_archive(path: str, region_code: str) -> _ParsedArchive:
    """Потоковый разбор ``gar_xml.zip``: три таблицы директории региона.

    Порядок членов в zip не гарантирован — таблицы разбираются явно по
    имени: сначала справочник адресообразующих объектов и дома, затем
    иерархия отфильтровывается по OBJECTID найденных домов.
    """
    member_re = re.compile(_MEMBER_RE_TEMPLATE.format(code=re.escape(region_code)), re.IGNORECASE)
    addr_names: dict[int, str] = {}
    houses: list[_HouseRow] = []
    paths: dict[int, str] = {}
    gone_houses: list[int] = []
    with zipfile.ZipFile(path) as archive:
        members: dict[str, str] = {}
        for name in archive.namelist():
            match = member_re.match(name)
            if match is not None:
                members[name] = match.group(2)
        for name, kind in members.items():
            if kind != "AS_ADDR_OBJ":
                continue
            with archive.open(name) as stream:
                for attrs in _iter_row_attrs(stream):
                    if not _active(attrs):
                        continue
                    name_part = attrs.get("NAME", "")
                    type_part = attrs.get("TYPENAME", "")
                    addr_names[int(attrs["OBJECTID"])] = (
                        f"{type_part} {name_part}".strip()
                    )
        house_ids: set[int] = set()
        for name, kind in members.items():
            if kind != "AS_HOUSES":
                continue
            with archive.open(name) as stream:
                for attrs in _iter_row_attrs(stream):
                    object_id = int(attrs["OBJECTID"])
                    if not _active(attrs):
                        gone_houses.append(object_id)
                        continue
                    houses.append(
                        _HouseRow(
                            object_id=object_id,
                            guid=attrs.get("OBJECTGUID", ""),
                            housenum=attrs.get("HOUSENUM", ""),
                            addnum1=attrs.get("ADDNUM1", ""),
                            addnum2=attrs.get("ADDNUM2", ""),
                        )
                    )
                    house_ids.add(object_id)
        for name, kind in members.items():
            if kind != "AS_ADM_HIERARCHY":
                continue
            with archive.open(name) as stream:
                for attrs in _iter_row_attrs(stream):
                    object_id = int(attrs["OBJECTID"])
                    if object_id in house_ids:
                        paths[object_id] = attrs.get("PATH", "")
    return _ParsedArchive(
        addr_names=addr_names, houses=houses, paths=paths, gone_houses=gone_houses
    )


_norm = address_match.norm
_street_norm = address_match.street_norm


def _canonical_name(
    addr_names: dict[int, str], path: str, house: _HouseRow
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
                        client,
                        region=region,
                        code=code,
                        last=last,
                        infos=all_infos,
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
        client: SmartProxyClient,
        *,
        region: str,
        code: str,
        last: _VersionInfo,
        infos: list[_VersionInfo],
    ) -> GarRegionSync:
        """План по курсору: дельта-цепочка к ``last`` или полная выгрузка."""
        cursor = await GeoSourceCursor.by_source_region(_SOURCE, region)
        done_version = (
            int(cursor.cursor)
            if cursor is not None and cursor.cursor.isdigit()
            else 0
        )
        if done_version >= last.version_id and (
            cursor is not None and cursor.status == GeoCursorStatus.DONE
        ):
            return GarRegionSync(status="current", version=done_version)
        pending = [info for info in infos if info.version_id > done_version]
        state_path = self._state_path(region)
        chain_ok = (
            bool(pending)
            and pending[-1].version_id >= last.version_id
            and len(pending) <= self._settings.gar_max_delta_chain
            and all(info.delta_url for info in pending)
            and state_path.exists()
        )
        try:
            if chain_ok:
                applied = 0
                matched = 0
                unresolved = 0
                for info in pending:
                    counts = await self._apply_archive(
                        client,
                        url=info.delta_url,
                        region=region,
                        code=code,
                        version=info.version_id,
                        mode="delta",
                    )
                    applied += 1
                    matched += counts.matched
                    unresolved += counts.unresolved
                _ = await GeoSourceCursor.upsert_progress(
                    source=_SOURCE,
                    region=region,
                    cursor=str(pending[-1].version_id),
                    rows_done=matched,
                    status=GeoCursorStatus.DONE,
                )
                return GarRegionSync(
                    status="done",
                    mode="delta",
                    versions=applied,
                    matched=matched,
                    unresolved=unresolved,
                )
            counts = await self._apply_archive(
                client,
                url=last.full_url,
                region=region,
                code=code,
                version=last.version_id,
                mode="full",
            )
            _ = await GeoSourceCursor.upsert_progress(
                source=_SOURCE,
                region=region,
                cursor=str(last.version_id),
                rows_done=counts.matched,
                status=GeoCursorStatus.DONE,
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

    async def _apply_archive(
        self,
        client: SmartProxyClient,
        *,
        url: str,
        region: str,
        code: str,
        version: int,
        mode: str,
    ) -> _ApplyCounts:
        """Скачать (resume) → распарсить → merge состояния → матч → enrich."""
        work_dir = Path(self._settings.gar_work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        local = work_dir / f"gar_{region}_{version}.zip"
        try:
            if url.startswith("file://"):
                archive_path = url.removeprefix("file://")
            else:
                await self._download(client, url=url, dest=local)
                archive_path = str(local)
            parsed = await asyncio.to_thread(_parse_archive, archive_path, code)
        finally:
            local.unlink(missing_ok=True)
        state, removed_guids = self._merge_state(region, parsed, mode=mode)
        return await self._match_and_apply(
            region=region,
            version=version,
            state=state,
            houses=parsed.houses,
            removed_guids=removed_guids,
        )

    def _state_path(self, region: str) -> Path:
        """Файл персистентного состояния региона в ``gar_work_dir``."""
        return Path(self._settings.gar_work_dir) / f"state_{region}.json"

    def _merge_state(
        self, region: str, parsed: _ParsedArchive, *, mode: str
    ) -> tuple[_GarState, list[str]]:
        """Слияние архива с состоянием региона; ``full`` заменяет его целиком.

        Возвращает состояние и GUID'ы домов, выведенных из ФИАС — их
        enrich-строки снимаются: источник больше не подтверждает объект.
        """
        state_path = self._state_path(region)
        previous = (
            _GarState.model_validate_json(state_path.read_text())
            if state_path.exists()
            else _GarState()
        )
        if mode == "full":
            state = _GarState(
                addr_names=parsed.addr_names,
                houses={house.object_id: house for house in parsed.houses},
                paths=parsed.paths,
            )
            removed_guids = [
                house.guid
                for object_id, house in previous.houses.items()
                if object_id not in state.houses and house.guid
            ]
        else:
            state = previous
            state.addr_names.update(parsed.addr_names)
            state.paths.update(parsed.paths)
            for house in parsed.houses:
                state.houses[house.object_id] = house
            removed_guids: list[str] = []
            for gone_id in parsed.gone_houses:
                gone = state.houses.pop(gone_id, None)
                if gone is not None and gone.guid:
                    removed_guids.append(gone.guid)
                _ = state.paths.pop(gone_id, None)
        _ = state_path.write_text(state.model_dump_json())
        return state, removed_guids

    async def _download(self, client: SmartProxyClient, *, url: str, dest: Path) -> None:
        """GET с resume по HTTP Range: частичный файл докачивается, а не перезаписывается."""
        size = dest.stat().st_size if dest.exists() else 0
        headers = {"Range": f"bytes={size}-"} if size else {}
        async with client.stream("GET", url, headers=headers) as response:
            _ = response.raise_for_status()
            append = size > 0 and response.status_code == 206
            mode = "ab" if append else "wb"
            with dest.open(mode) as out:
                async for chunk in response.aiter_bytes(1 << 20):
                    _ = out.write(chunk)

    async def _match_and_apply(
        self,
        *,
        region: str,
        version: int,
        state: _GarState,
        houses: list[_HouseRow],
        removed_guids: list[str],
    ) -> _ApplyCounts:
        """Матч домов к справочнику → enrich bulk + живые колонки + очередь."""
        generation = await GeoImportState.active_generation()
        _ = await GeoAddressEnrich.delete_by_guids(removed_guids)
        _ = await GeoAddress.clear_gar_attrs(
            guids=removed_guids, generation=generation
        )
        candidates = await GeoAddress.list_for_enrich_match(
            region=region, generation=generation
        )
        by_num: dict[str, list[GeoAddress]] = {}
        for row in candidates:
            by_num.setdefault(_norm(row.housenumber), []).append(row)
        matched_rows: list[tuple[str, int, str, str]] = []
        unresolved: list[JsonObject] = []
        for house in houses:
            path = state.paths.get(house.object_id, "")
            canonical = _canonical_name(state.addr_names, path, house)
            street_name, path_names = self._street_of(path, state.addr_names)
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
            matched_rows.append((hit.osm_type, hit.osm_id, house.guid, canonical))
        written = await GeoAddressEnrich.bulk_upsert(matched_rows)
        _ = await GeoAddress.bulk_set_gar_attrs(matched_rows, generation=generation)
        enqueued = await GeoEnrichItem.enqueue_missing(
            kind=UNRESOLVED_KIND,
            payloads=unresolved,
            dedupe_field="gar_objectid",
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
            rows=len(unresolved),
        )
        _logger.info(
            "geo.gar.apply_done",
            region=region,
            version=version,
            houses=len(houses),
            matched=len(matched_rows),
            unresolved=len(unresolved),
        )
        return _ApplyCounts(
            houses=len(houses),
            matched=len(matched_rows),
            unresolved=len(unresolved),
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
        house: _HouseRow,
        street_name: str,
        path_names: set[str],
        by_num: dict[str, list[GeoAddress]],
    ) -> GeoAddress | None:
        """Лучший кандидат по номеру дома + схожести улицы; ``None`` — промах."""
        variants = {_norm(house.housenum)}
        if house.addnum1:
            variants.add(_norm(f"{house.housenum}к{house.addnum1}"))
            variants.add(_norm(f"{house.housenum}{house.addnum1}"))
        if house.addnum2:
            variants.add(_norm(f"{house.housenum}стр{house.addnum2}"))
            variants.add(_norm(f"{house.housenum}{house.addnum2}"))
        best: GeoAddress | None = None
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
