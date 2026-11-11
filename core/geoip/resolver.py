"""IP→страна по DB-IP Lite (``dbip-country-lite-*.csv.gz``, CC-BY 4.0).

Файл скачивается в Dockerfile (``ARG GEOIP_DB_VERSION``) в
``/app/data/geoip/dbip-country.csv.gz``; тесты подменяют ``db_path`` на fixture.
CSV — ``start_ip,end_ip,cc`` строки без кавычек, диапазоны непрерывны и
покрывают всё адресное пространство (``ZZ`` — неразмеченное). Таблицы держатся
в памяти как два отсортированных ``array('Q')`` + параллельные ``array('H')``
индексов стран: ~700К диапазонов ≈ 12MB RAM, lookup — bisect за микросекунды.
"""

from __future__ import annotations

import gzip
import ipaddress
import threading
from array import array
from bisect import bisect_right
from pathlib import Path

from core.config.models import GeoIpConfig
from core.logging import get_logger

logger = get_logger(__name__)


class _RangeTable:
    """Сортированные диапазоны одного адресного семейства.

    v4 держится в ``array('Q')``; v6 — в обычных списках (128-битные int
    не влезают в 'Q'). """

    __slots__ = ("starts", "ends", "cc_index")

    def __init__(self, *, ipv4: bool) -> None:
        ints: array[int] | list[int] = array("Q") if ipv4 else []
        self.starts: array[int] | list[int] = ints
        self.ends: array[int] | list[int] = array("Q") if ipv4 else []
        self.cc_index = array("H")


class GeoIpResolver:
    """Лениво загружаемый резолвер IP→ISO-3166 alpha-2 (``""`` — нет данных)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._tables: dict[int, _RangeTable] = {}
        # Индекс 0 — ZZ/unknown/private: country_of отдаёт "".
        self._countries: list[str] = [""]
        self._lock = threading.Lock()
        self._loaded = False

    def country_of(self, ip: str) -> str:
        """ISO-код страны или ``""`` — unknown/reserved/private."""
        if not ip:
            return ""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return ""
        table = self._table(addr.max_prefixlen == 32)
        if table is None:
            return ""
        value = int(addr)
        idx = bisect_right(table.starts, value) - 1
        if idx < 0 or value > table.ends[idx]:
            return ""
        return self._countries[table.cc_index[idx]]

    def _table(self, ipv4: bool) -> _RangeTable | None:
        if not self._loaded:
            self._load()
        return self._tables.get(4 if ipv4 else 6)

    def _load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            if not self._db_path.is_file():
                raise FileNotFoundError(
                    f"GeoIP: база не найдена: {self._db_path} "
                    "(в образе кладётся Dockerfile ARG GEOIP_DB_VERSION)"
                )
            cc_ids: dict[str, int] = {"ZZ": 0}
            tables = {4: _RangeTable(ipv4=True), 6: _RangeTable(ipv4=False)}
            rows = 0
            with gzip.open(self._db_path, "rt", encoding="ascii") as fh:
                for line in fh:
                    start_s, end_s, cc = line.rstrip("\n").split(",", 2)
                    cc_idx = cc_ids.get(cc)
                    if cc_idx is None:
                        cc_idx = len(self._countries)
                        cc_ids[cc] = cc_idx
                        self._countries.append(cc)
                    table = tables[6 if ":" in start_s else 4]
                    table.starts.append(int(ipaddress.ip_address(start_s)))
                    table.ends.append(int(ipaddress.ip_address(end_s)))
                    table.cc_index.append(cc_idx)
                    rows += 1
            self._tables = tables
            self._loaded = True
            logger.info(
                "geoip.loaded",
                rows=rows,
                countries=len(self._countries) - 1,
                db_path=str(self._db_path),
            )


_resolver: GeoIpResolver | None = None
_resolver_lock = threading.Lock()


def get_geoip_resolver(config: GeoIpConfig | None = None) -> GeoIpResolver:
    """Процессный singleton резолвера; конфиг — settings.geoip."""
    global _resolver
    if _resolver is None:
        with _resolver_lock:
            if _resolver is None:
                _resolver = GeoIpResolver((config or GeoIpConfig()).db_path)
    return _resolver


def reset_geoip_resolver() -> None:
    """Сброс singleton — только для тестов."""
    global _resolver
    with _resolver_lock:
        _resolver = None


__all__ = [
    "GeoIpResolver",
    "get_geoip_resolver",
    "reset_geoip_resolver",
]
