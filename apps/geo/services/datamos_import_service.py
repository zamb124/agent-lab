"""Импортёр Портала открытых данных Москвы (apidata.mos.ru).

``GET /v1/datasets/{id}/rows?$top&$skip&api_key=`` →
``{Count, Rows: [{Id, Number, Cells: {...}}]}`` — официальные датасеты
города (``data_mos_datasets``: ``dataset_id → entity_kind``; v1 —
``address``, адресный реестр). Пагинация ``$skip``/$top с resume-курсором
``geo_source_cursors(source='data_mos_ru', region='<region>:<dataset>')``;
тик читает ``data_mos_tick_pages`` страниц и продолжает со следующего.

Строки kind ``address``: ``Cells.ADDRESS`` + ``geoData.coordinates`` →
матч к ``geo_addresses`` (номер дома из хвоста адреса + схожесть улицы,
``data_mos_match_similarity``) → ``canonical_name`` в ``geo_address_enrich``.
Без ``data_mos_api_key`` — ``skipped=no_api_key`` (фича выключается конфигом).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from difflib import SequenceMatcher

from pydantic import BaseModel

from apps.geo.config import GeoSettings
from apps.geo.db.import_lock import geo_import_lock
from apps.geo.models.geo_address import GeoAddress
from apps.geo.models.geo_address_enrich import GeoAddressEnrich
from apps.geo.models.geo_import_state import GeoImportState
from apps.geo.models.geo_region import GeoRegion
from apps.geo.models.geo_source import GeoSource
from apps.geo.models.geo_source_cursor import GeoCursorStatus, GeoSourceCursor
from apps.geo.models.geo_stats import GeoStats
from apps.geo.services import address_match
from core.http import get_httpx_client
from core.http.client import SmartProxyClient
from core.logging import get_logger
from core.types import JsonObject

_SOURCE = "data_mos_ru"
_LOCK_KEY = "geo.datamos_sync"

_logger = get_logger(__name__)

# «… ул. Тверская, д. 1» / «… Никольская улица, 10»: улица — до последней
# запятой-дома, дом — хвост после «д.|дом|вл.|корп.|стр.» или после запятой.
_HOUSE_TAIL_RE = re.compile(
    r"^(?P<street>.+?)[,\s]+(?:д\.?|дом|вл\.?|владение|корп\.?|стр\.?)\s*" +
    r"(?P<house>[0-9А-Яа-я][0-9А-Яа-я/\-]*)\s*$"
)
_HOUSE_COMMA_RE = re.compile(r"^(?P<street>.+?),\s*(?P<house>\d+[0-9А-Яа-я/\-]*)\s*$")


class _RowsPage(BaseModel):
    """Страница ``/v1/datasets/{id}/rows``."""

    Count: int = 0
    Rows: list[JsonObject] = []


class DataMosSyncResult(BaseModel):
    """Итог тика: ``skipped`` — причина пропуска, иначе по ``region:dataset``."""

    skipped: str = ""
    datasets: dict[str, JsonObject] = {}


def _parse_address(raw: str) -> tuple[str, str]:
    """``(street, housenumber)`` из строки адреса датасета."""
    for pattern in (_HOUSE_TAIL_RE, _HOUSE_COMMA_RE):
        match = pattern.match(raw.strip())
        if match:
            # «г. Москва, ул. Тверская» → последний сегмент — сама улица.
            street = match.group("street").strip(" ,").split(",")[-1].strip()
            if street:
                return street, match.group("house")
    return "", ""


class DataMosImportService:
    """Тик синка датасетов: страницы → адресные строки → enrich-матч."""

    def __init__(self, settings: GeoSettings) -> None:
        self._settings: GeoSettings = settings

    async def run_sync(self) -> DataMosSyncResult:
        """Тик: страницы датасетов → матч адресов → ``canonical_name``."""
        if not self._settings.data_mos_sync_enabled:
            return DataMosSyncResult(skipped="data_mos_sync_disabled")
        if not self._settings.data_mos_api_key:
            return DataMosSyncResult(skipped="no_api_key")
        source = await GeoSource.by_name(_SOURCE)
        if source is not None and not source.enabled:
            return DataMosSyncResult(skipped="source_disabled")
        if not self._settings.data_mos_datasets:
            return DataMosSyncResult(skipped="no_datasets")
        regions = await GeoRegion.list_enabled_by_name_asc()
        if not regions:
            return DataMosSyncResult(skipped="no_regions")
        async with geo_import_lock(
            self._settings.database.geo_url, key=_LOCK_KEY
        ) as acquired:
            if not acquired:
                return DataMosSyncResult(skipped="locked")
            async with get_httpx_client(
                timeout=self._settings.data_mos_http_timeout_seconds
            ) as client:
                generation = await GeoImportState.active_generation()
                datasets: dict[str, JsonObject] = {}
                for region in regions:
                    candidates = await GeoAddress.list_for_enrich_match(
                        region=region.name, generation=generation
                    )
                    for dataset_id, kind in self._settings.data_mos_datasets.items():
                        datasets[f"{region.name}:{dataset_id}"] = (
                            await self._sync_dataset(
                                client,
                                region=region.name,
                                dataset_id=dataset_id,
                                kind=kind,
                                candidates=candidates,
                            )
                        )
                return DataMosSyncResult(datasets=datasets)

    async def _sync_dataset(
        self,
        client: SmartProxyClient,
        *,
        region: str,
        dataset_id: str,
        kind: str,
        candidates: list[GeoAddress],
    ) -> JsonObject:
        """Страницы датасета: ``$skip``-курсор → строки → enrich-матч."""
        cursor_key = f"{region}:{dataset_id}"
        cursor = await GeoSourceCursor.by_source_region(_SOURCE, cursor_key)
        skip = (
            int(cursor.cursor)
            if cursor is not None and cursor.cursor.isdigit()
            else 0
        )
        if (
            cursor is not None
            and cursor.status == GeoCursorStatus.DONE
            and skip > 0
        ):
            return {"status": "current", "skip": skip}
        by_num: dict[str, list[GeoAddress]] = {}
        for row in candidates:
            by_num.setdefault(address_match.norm(row.housenumber), []).append(row)
        matched = 0
        processed = 0
        try:
            for _page in range(self._settings.data_mos_tick_pages):
                page = await self._fetch_page(client, dataset_id, skip)
                if not page.Rows:
                    break
                for row in page.Rows:
                    processed += 1
                    matched += await self._apply_row(
                        kind=kind, row=row, by_num=by_num
                    )
                skip += len(page.Rows)
                done = len(page.Rows) < self._settings.data_mos_page_size
                _ = await GeoSourceCursor.upsert_progress(
                    source=_SOURCE,
                    region=cursor_key,
                    cursor=str(skip),
                    rows_done=matched,
                    status=(
                        GeoCursorStatus.DONE
                        if done
                        else GeoCursorStatus.RUNNING
                    ),
                )
                if done:
                    break
        except Exception as exc:
            await GeoSourceCursor.mark_failed(
                source=_SOURCE,
                region=cursor_key,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        await GeoStats.set_rows(
            generation=0,
            source=_SOURCE,
            region=region,
            entity=f"dataset_{kind}",
            rows=matched,
        )
        return {"status": "done", "skip": skip, "rows": processed, "matched": matched}

    async def _fetch_page(
        self, client: SmartProxyClient, dataset_id: str, skip: int
    ) -> _RowsPage:
        """``GET /v1/datasets/{id}/rows?$top&$skip&api_key=``."""
        response = await client.get(
            f"{self._settings.data_mos_base_url}/v1/datasets/{dataset_id}/rows",
            params={
                "$top": str(self._settings.data_mos_page_size),
                "$skip": str(skip),
                "api_key": self._settings.data_mos_api_key,
            },
        )
        _ = response.raise_for_status()
        return _RowsPage.model_validate_json(response.content)

    async def _apply_row(
        self,
        *,
        kind: str,
        row: JsonObject,
        by_num: dict[str, list[GeoAddress]],
    ) -> int:
        """Одна строка датасета → enrich при уверенном матче адреса."""
        if kind != "address":
            return 0
        cells = row.get("Cells")
        if not isinstance(cells, dict):
            return 0
        raw_address = str(cells.get("ADDRESS", "") or cells.get("Address", ""))
        street, housenum = _parse_address(raw_address)
        if not housenum:
            return 0
        hit = self._match(street, housenum, by_num)
        if hit is None:
            return 0
        canonical = raw_address.strip() or hit.display_name
        _ = await GeoAddressEnrich.upsert_by_object(
            GeoAddressEnrich(
                osm_type=hit.osm_type,
                osm_id=hit.osm_id,
                canonical_name=canonical,
                cadastral_number=(
                    str(cells.get("CAD_NUM", ""))
                    if cells.get("CAD_NUM")
                    else ""
                ),
                updated_at=datetime.now(UTC),
            )
        )
        return 1

    def _match(
        self,
        street: str,
        housenum: str,
        by_num: dict[str, list[GeoAddress]],
    ) -> GeoAddress | None:
        """Лучший кандидат по номеру дома + схожести улицы; ``None`` — промах."""
        target = address_match.street_norm(street)
        best: GeoAddress | None = None
        best_score = 0.0
        for candidate in by_num.get(address_match.norm(housenum), []):
            cand_street = address_match.street_norm(candidate.street)
            score = (
                1.0
                if target and target in cand_street
                else SequenceMatcher(None, target, cand_street).ratio()
            )
            if score > best_score:
                best = candidate
                best_score = score
        if best is None or best_score < self._settings.data_mos_match_similarity:
            return None
        return best
