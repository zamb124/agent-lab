"""Юнит-тесты ``core.geoip``: загрузка DB-IP CSV, bisect-lookup v4/v6, края."""

from __future__ import annotations

import gzip
import time
from pathlib import Path

import pytest

from core.geoip.resolver import GeoIpResolver

_CSV = (
    # v4: покрытие с дырой 4.0.0.0-7.255.255.255 (немапнутый сегмент)
    "0.0.0.0,0.255.255.255,ZZ\n"
    "1.0.0.0,3.255.255.255,AU\n"
    "8.8.8.8,8.8.8.8,US\n"
    "8.8.8.9,77.255.255.255,ZZ\n"
    "78.0.0.0,78.255.255.255,RU\n"
    "79.0.0.0,255.255.255.255,ZZ\n"
    # v6: спарсная таблица
    "2001:4860:4860::8888,2001:4860:4860::8888,US\n"
    "2a00::,2aff:ffff:ffff:ffff:ffff:ffff:ffff:ffff,NL\n"
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "dbip-country.csv.gz"
    with gzip.open(path, "wt", encoding="ascii") as fh:
        fh.write(_CSV)
    return path


def test_ipv4_lookup(db_path: Path) -> None:
    resolver = GeoIpResolver(str(db_path))
    assert resolver.country_of("8.8.8.8") == "US"
    assert resolver.country_of("1.1.1.1") == "AU"
    assert resolver.country_of("78.31.96.1") == "RU"


def test_ipv4_unmapped_and_reserved(db_path: Path) -> None:
    resolver = GeoIpResolver(str(db_path))
    # Дыра между диапазонами (4.x–7.x) — нет данных.
    assert resolver.country_of("4.4.4.4") == ""
    # ZZ — резерв/немапнутое покрытие.
    assert resolver.country_of("0.1.2.3") == ""
    # Приватные адреса в базе не описаны (DB-IP их не несёт) — пусто.
    assert resolver.country_of("10.0.0.1") == ""
    assert resolver.country_of("127.0.0.1") == ""


def test_ipv6_lookup(db_path: Path) -> None:
    resolver = GeoIpResolver(str(db_path))
    assert resolver.country_of("2001:4860:4860::8888") == "US"
    assert resolver.country_of("2a01:ff00::1") == "NL"
    assert resolver.country_of("::1") == ""


def test_malformed_and_empty() -> None:
    resolver = GeoIpResolver("/nonexistent/anyway.csv.gz")
    assert resolver.country_of("") == ""
    assert resolver.country_of("not-an-ip") == ""
    assert resolver.country_of("999.999.999.999") == ""


def test_missing_db_raises(tmp_path: Path) -> None:
    resolver = GeoIpResolver(str(tmp_path / "absent.csv.gz"))
    with pytest.raises(FileNotFoundError):
        resolver.country_of("8.8.8.8")


def test_lookup_is_microseconds(db_path: Path) -> None:
    resolver = GeoIpResolver(str(db_path))
    resolver.country_of("8.8.8.8")  # прогрев — загрузка файла
    started = time.perf_counter()
    for _ in range(10_000):
        resolver.country_of("78.31.96.1")
    elapsed = time.perf_counter() - started
    assert elapsed < 1.0, f"10k lookups заняли {elapsed:.2f}s — bisect деградировал"
