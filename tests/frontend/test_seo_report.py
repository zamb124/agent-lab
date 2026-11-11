"""Юнит-тесты ``scripts.seo.report``: агрегаты, HTML-отчёт, отсылки Telegram."""

from __future__ import annotations

import json
import sys
from typing import cast

import pytest

from scripts.seo import report as seo_report


def _counts(overrides: dict[str, object], key: str, default: dict[str, int]) -> dict[str, int]:
    value = overrides.get(key, default)
    return cast(dict[str, int], value)


def _int(overrides: dict[str, object], key: str, default: int) -> int:
    return cast(int, overrides.get(key, default))


def _stats(**overrides: object) -> seo_report.VisitStats:
    """VisitStats с реалистичными агрегатами; ``overrides`` подменяет поля."""
    defaults: dict[str, object] = {
        "hours": 1,
        "unique": 7,
        "humans": 12,
        "bots": 30,
        "surface_human": {"page": 9, "docs": 3},
        "surface_bot": {"docs": 20, "sitemap": 6, "page": 4},
        "country": {"RU": 8, "DE": 3, "US": 1},
        "referer": {"www.google.com": 5, "yandex.ru": 2},
        "bot_family": {"yandexbot": 15, "gptbot": 9, "googlebot": 6},
        "path_human": {
            "/products/rag": 4,
            "/documentation/scenarios/shop/": 3,
            "/": 2,
        },
        "path_bot": {
            "/sitemap.xml": 6,
            "/documentation/llms-full.txt": 9,
            "/en/products/geo": 5,
        },
    }
    return seo_report.VisitStats(
        hours=_int(overrides, "hours", cast(int, defaults["hours"])),
        unique=_int(overrides, "unique", cast(int, defaults["unique"])),
        humans=_int(overrides, "humans", cast(int, defaults["humans"])),
        bots=_int(overrides, "bots", cast(int, defaults["bots"])),
        surface_human=_counts(overrides, "surface_human", cast(dict[str, int], defaults["surface_human"])),
        surface_bot=_counts(overrides, "surface_bot", cast(dict[str, int], defaults["surface_bot"])),
        country=_counts(overrides, "country", cast(dict[str, int], defaults["country"])),
        referer=_counts(overrides, "referer", cast(dict[str, int], defaults["referer"])),
        bot_family=_counts(overrides, "bot_family", cast(dict[str, int], defaults["bot_family"])),
        path_human=_counts(overrides, "path_human", cast(dict[str, int], defaults["path_human"])),
        path_bot=_counts(overrides, "path_bot", cast(dict[str, int], defaults["path_bot"])),
    )


def _empty_stats() -> seo_report.VisitStats:
    return _stats(
        unique=0, humans=0, bots=0,
        surface_human={}, surface_bot={}, country={}, referer={},
        bot_family={}, path_human={}, path_bot={},
    )


def test_to_counts_sums_duplicate_labels() -> None:
    rows = [
        ({"country": "RU"}, 3.0),
        ({"country": "RU"}, 4.0),
        ({"country": "DE"}, 2.0),
        ({"other": "x"}, 9.0),
    ]
    assert seo_report.to_counts(rows, "country") == {"RU": 7, "DE": 2}


def test_top_lines_sorted_and_limited() -> None:
    counts = {f"k{i}": i for i in range(15)}
    lines = seo_report.top_lines(counts, limit=5)
    assert len(lines) == 5
    assert "14" in lines[0] and "k14" in lines[0]
    assert "k9" not in "\n".join(lines)


def test_report_contains_all_sections() -> None:
    stats = _stats()
    text = seo_report.build_report(stats)
    assert "SEO-отчёт · последние 1 ч" in text
    assert "7" in text and "12" in text and "30" in text
    assert "RU" in text and "DE" in text
    assert "www.google.com" in text
    assert "yandexbot" in text and "gptbot" in text
    assert "/products/rag" in text
    # Документация — обязательный отдельный блок, пути людей+ботов слиты.
    assert "Документация" in text
    assert "/documentation/scenarios/shop/" in text
    assert "/documentation/llms-full.txt" in text
    assert "/en/products/geo" in text


def test_report_escapes_html() -> None:
    stats = _stats(path_human={"/x?<b>&q": 3}, path_bot={})
    text = seo_report.build_report(stats)
    assert "<b>&q" not in text.replace("<b>SEO", "", 1) or "&lt;b&gt;" in text


def test_report_only_nonempty_sections() -> None:
    stats = _stats(country={}, referer={}, path_bot={})
    text = seo_report.build_report(stats)
    assert "Страны (люди)" not in text
    assert "Откуда пришли" not in text
    assert "Страницы (боты)" not in text
    assert "Документация" in text  # docs-пути людей ещё есть


def test_report_truncates_over_limit() -> None:
    stats = _stats(path_human={f"/p/{i}": 100 - i for i in range(300)})
    text = seo_report.build_report(stats)
    assert len(text) <= seo_report.TELEGRAM_LIMIT


def test_loki_vector_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "data": {"result": [
            {"metric": {"surface": "docs"}, "value": [1700000000, "42"]},
            {"metric": {"surface": "page"}, "value": [1700000000, "7"]},
        ]}
    }

    class _Resp:
        status_code: int = 200
        text: str = json.dumps(payload)

        def raise_for_status(self) -> None:
            return None

    called: dict[str, object] = {}

    def _get(url: str, **kwargs: object) -> _Resp:
        called["url"] = url
        called["params"] = kwargs.get("params")
        return _Resp()

    monkeypatch.setattr(seo_report.httpx2, "get", _get)  # pyright: ignore[reportPrivateLocalImportUsage]
    rows = seo_report.loki_vector("http://loki:3100", "expr")
    assert rows == [({"surface": "docs"}, 42.0), ({"surface": "page"}, 7.0)]
    assert called["url"] == "http://loki:3100/loki/api/v1/query"
    assert called["params"] == {"query": "expr"}


def test_collect_stats_maps_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    canned: dict[str, list[tuple[dict[str, str], float]]] = {
        "unique": [({"visitor": "a"}, 5.0), ({"visitor": "b"}, 2.0)],
        "surface_human": [({"surface": "page"}, 10.0)],
        "surface_bot": [({"surface": "docs"}, 20.0)],
        "country": [({"country": "RU"}, 10.0)],
        "referer": [({"referer": "google.com"}, 4.0)],
        "bot_family": [({"ua_family": "gptbot"}, 20.0)],
        "path_human": [({"path": "/"}, 10.0)],
        "path_bot": [({"path": "/documentation/x"}, 20.0)],
    }

    def _loki(_url: str, expr: str) -> list[tuple[dict[str, str], float]]:
        name = next(k for k, q in seo_report.queries(1).items() if q == expr)
        return canned[name]

    monkeypatch.setattr(seo_report, "loki_vector", _loki)
    stats = seo_report.collect_stats("http://loki:3100", 1)
    assert stats.unique == 7
    assert stats.humans == 10 and stats.bots == 20
    assert stats.bot_family == {"gptbot": 20}
    assert stats.path_bot == {"/documentation/x": 20}


def test_send_telegram_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}

    class _Resp:
        status_code: int = 200

    def _post(url: str, **kwargs: object) -> _Resp:
        sent["url"] = url
        sent["json"] = kwargs["json"]
        return _Resp()

    monkeypatch.setattr(seo_report.httpx2, "post", _post)  # pyright: ignore[reportPrivateLocalImportUsage]
    status = seo_report.send_telegram("tok", "chat1", "hello")
    assert status == 200
    assert sent["url"] == "https://api.telegram.org/bottok/sendMessage"
    body = cast(dict[str, object], sent["json"])
    assert body["chat_id"] == "chat1"
    assert body["parse_mode"] == "HTML"
    assert body["disable_web_page_preview"] is True


def test_main_skips_when_no_visits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _collect(_url: str, _hours: int) -> seo_report.VisitStats:
        return _empty_stats()

    monkeypatch.setattr(seo_report, "collect_stats", _collect)
    monkeypatch.setattr(
        sys, "argv", ["report", "--loki-url", "http://x"]
    )
    assert seo_report.main() == 0
    out = capsys.readouterr().out
    assert "seo.report_skipped" in out


def test_main_sends_when_visits(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _collect(_url: str, _hours: int) -> seo_report.VisitStats:
        return _stats()

    def _send(_token: str, _chat: str, _text: str) -> int:
        return 200

    monkeypatch.setattr(seo_report, "collect_stats", _collect)
    monkeypatch.setattr(seo_report, "send_telegram", _send)
    monkeypatch.setenv("TELEGRAM_ALERTS_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALERTS_CHAT_ID", "chat")
    monkeypatch.setattr(sys, "argv", ["report"])
    assert seo_report.main() == 0
    assert "seo.report_sent" in capsys.readouterr().out


def test_main_failed_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _collect(_url: str, _hours: int) -> seo_report.VisitStats:
        return _stats()

    def _send(_token: str, _chat: str, _text: str) -> int:
        return 403

    monkeypatch.setattr(seo_report, "collect_stats", _collect)
    monkeypatch.setattr(seo_report, "send_telegram", _send)
    monkeypatch.setenv("TELEGRAM_ALERTS_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALERTS_CHAT_ID", "chat")
    monkeypatch.setattr(sys, "argv", ["report"])
    assert seo_report.main() == 1
    assert "seo.report_failed" in capsys.readouterr().out


def test_queries_reference_seo_visit_stream() -> None:
    for name, expr in seo_report.queries(24).items():
        assert 'message="seo.visit"' in expr
        assert "[24h]" in expr, name
