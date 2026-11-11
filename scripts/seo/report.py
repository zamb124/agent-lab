"""SEO-отчёт в Telegram-канал алертов: кто ходил на публичную поверхность.

CronJob ``seo-report`` (``70-observability``) раз в час собирает агрегаты
``seo.visit`` из Loki instant API и шлёт HTML-сообщение в тот же чат
LinnexAlerts, что и Grafana (env ``TELEGRAM_ALERTS_BOT_TOKEN`` /
``TELEGRAM_ALERTS_CHAT_ID``, ``HTTPS_PROXY`` из platform-secrets —
api.telegram.org недоступен из кластера напрямую).

Пустой час отчётом не спамит: ``seo.report_skipped`` + выход 0 (молчание
канала при нулевом трафике ловит алерт ``seo-visits-silent``). Финальная
строка — машинная ``{"message": "seo.report_sent|seo.report_failed|seo.report_skipped"}``.

Запуск вручную:
    uv run python -m scripts.seo.report --hours 24 --loki-url http://127.0.0.1:3100
    uv run python -m scripts.seo.report --dry-run   # сверстать сообщение, не слать
"""

from __future__ import annotations

import argparse
import dataclasses
import html
import json
import os

import httpx2

from core.types import parse_json_object

_LOKI_DEFAULT_URL = "http://loki.platform.svc.cluster.local:3100"
_TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_LIMIT = 4096
TOP_N = 10
_VISIT = '{service="frontend",log_type="seo"} | json | message="seo.visit"'


def queries(hours: int) -> dict[str, str]:
    w = f"{hours}h"
    return {
        "unique": f'sum(count by (visitor) (count_over_time({_VISIT} | visitor!="" [{w}])))',
        "surface_human": f'sum by (surface) (count_over_time({_VISIT} | bot="false" [{w}]))',
        "surface_bot": f'sum by (surface) (count_over_time({_VISIT} | bot="true" [{w}]))',
        "country": f'sum by (country) (count_over_time({_VISIT} | bot="false" | country!="" [{w}]))',
        "referer": (
            f'sum by (referer) (count_over_time({_VISIT} | bot="false" '
            f'| referer!="direct" | referer!="internal" [{w}]))'
        ),
        "bot_family": f'sum by (ua_family) (count_over_time({_VISIT} | bot="true" [{w}]))',
        "path_human": f'sum by (path) (count_over_time({_VISIT} | bot="false" [{w}]))',
        "path_bot": f'sum by (path) (count_over_time({_VISIT} | bot="true" [{w}]))',
    }


def loki_vector(loki_url: str, expr: str) -> list[tuple[dict[str, str], float]]:
    """Instant-запрос к Loki: ``[(labels, value)]`` из ``data.result[].value``."""
    response = httpx2.get(
        f"{loki_url}/loki/api/v1/query",
        params={"query": expr},
        timeout=30.0,
    )
    _ = response.raise_for_status()
    body = parse_json_object(response.text, "loki_response")
    rows: list[tuple[dict[str, str], float]] = []
    data = body.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, list):
        return rows
    for entry in result:
        if not isinstance(entry, dict):
            continue
        metric = entry.get("metric")
        value = entry.get("value")
        if (
            not isinstance(metric, dict)
            or not isinstance(value, list)
            or len(value) != 2
        ):
            continue
        rows.append(({str(k): str(v) for k, v in metric.items()}, float(str(value[1]))))
    return rows


def to_counts(rows: list[tuple[dict[str, str], float]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for labels, value in rows:
        name = labels.get(key, "")
        if name:
            counts[name] = counts.get(name, 0) + int(value)
    return counts


@dataclasses.dataclass
class VisitStats:
    hours: int
    unique: int
    humans: int
    bots: int
    surface_human: dict[str, int]
    surface_bot: dict[str, int]
    country: dict[str, int]
    referer: dict[str, int]
    bot_family: dict[str, int]
    path_human: dict[str, int]
    path_bot: dict[str, int]

    @property
    def total(self) -> int:
        return self.humans + self.bots


def collect_stats(loki_url: str, hours: int) -> VisitStats:
    """Все агрегаты за ``hours`` часов одним проходом по Loki."""
    results = {
        name: loki_vector(loki_url, expr) for name, expr in queries(hours).items()
    }
    unique = int(sum(v for _m, v in results["unique"]))
    surface_human = to_counts(results["surface_human"], "surface")
    surface_bot = to_counts(results["surface_bot"], "surface")
    return VisitStats(
        hours=hours,
        unique=unique,
        humans=sum(surface_human.values()),
        bots=sum(surface_bot.values()),
        surface_human=surface_human,
        surface_bot=surface_bot,
        country=to_counts(results["country"], "country"),
        referer=to_counts(results["referer"], "referer"),
        bot_family=to_counts(results["bot_family"], "ua_family"),
        path_human=to_counts(results["path_human"], "path"),
        path_bot=to_counts(results["path_bot"], "path"),
    )


def _esc(value: str) -> str:
    return html.escape(value, quote=False)


def top_lines(counts: dict[str, int], limit: int = TOP_N, *,
               key_width: int = 0) -> list[str]:
    """``count · key`` строки по убыванию; одинаковые count — по имени."""
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    if not items:
        return []
    width = key_width or max(len(str(v)) for v, _k in items)
    return [f"<code>{count:>{width}}</code> · {_esc(name)}" for name, count in items]


def _inline_top(counts: dict[str, int], limit: int = TOP_N) -> str:
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return " · ".join(f"{_esc(name)} {count}" for name, count in items)


def _doc_paths(stats: VisitStats) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in (stats.path_human, stats.path_bot):
        for path, count in source.items():
            if "documentation" in path:
                merged[path] = merged.get(path, 0) + count
    return merged


def build_report(stats: VisitStats) -> str:
    """HTML-сообщение отчёта (Telegram ``parse_mode=HTML``)."""
    lines: list[str] = [
        f"<b>SEO-отчёт · последние {stats.hours} ч</b>",
        "",
        f"Посетителей: <b>{stats.unique}</b> уникальных · люди <b>{stats.humans}</b> · боты <b>{stats.bots}</b>",
    ]
    surfaces = _inline_top({
        name: stats.surface_human.get(name, 0) + stats.surface_bot.get(name, 0)
        for name in stats.surface_human.keys() | stats.surface_bot.keys()
    })
    if surfaces:
        lines += ["", f"<b>Поверхности:</b> {surfaces}"]
    if stats.country:
        lines += ["", "<b>Страны (люди)</b>", *top_lines(stats.country)]
    if stats.referer:
        lines += ["", "<b>Откуда пришли (люди)</b>", *top_lines(stats.referer)]
    if stats.bot_family:
        lines += ["", "<b>Краулеры / LLM-боты</b>", *top_lines(stats.bot_family)]
    if stats.path_human:
        lines += ["", "<b>Страницы (люди)</b>", *top_lines(stats.path_human)]
    doc_paths = _doc_paths(stats)
    if doc_paths:
        lines += ["", "<b>Документация</b>", *top_lines(doc_paths)]
    if stats.path_bot:
        lines += ["", "<b>Страницы (боты)</b>", *top_lines(stats.path_bot)]
    text = "\n".join(lines)
    if len(text) > TELEGRAM_LIMIT - 64:
        text = text[: TELEGRAM_LIMIT - 80] + "\n…"
    return text


def send_telegram(token: str, chat_id: str, text: str) -> int:
    """POST sendMessage → HTTP status. Прокси — через env HTTPS_PROXY."""
    response = httpx2.post(
        f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30.0,
    )
    return response.status_code


def _emit_event(event: str, *, hours: int, visits: int, http_status: int | None) -> None:
    print(json.dumps({
        "message": event,
        "level": "WARNING" if event.endswith("failed") else "INFO",
        "hours": hours,
        "visits": visits,
        "http_status": http_status,
    }, ensure_ascii=False))


@dataclasses.dataclass
class _Args:
    hours: int = 1
    loki_url: str = _LOKI_DEFAULT_URL
    dry_run: bool = False


def main() -> int:
    parser = argparse.ArgumentParser(description="SEO hourly report → Telegram")
    _ = parser.add_argument("--hours", type=int, default=1)
    _ = parser.add_argument("--loki-url", default=os.environ.get("SEO_REPORT_LOKI_URL", _LOKI_DEFAULT_URL))
    _ = parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(namespace=_Args())

    stats = collect_stats(args.loki_url, args.hours)
    text = build_report(stats)
    if args.dry_run:
        print(text)
        return 0
    if stats.total == 0:
        _emit_event("seo.report_skipped", hours=args.hours, visits=0, http_status=None)
        return 0
    token = os.environ.get("TELEGRAM_ALERTS_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALERTS_CHAT_ID", "")
    if not token or not chat_id:
        print("seo.report: нет TELEGRAM_ALERTS_BOT_TOKEN/CHAT_ID")
        _emit_event("seo.report_skipped", hours=args.hours, visits=stats.total, http_status=None)
        return 0
    try:
        status = send_telegram(token, chat_id, text)
    except httpx2.HTTPError as exc:
        print(f"seo.report: transport error: {exc}")
        _emit_event("seo.report_failed", hours=args.hours, visits=stats.total, http_status=None)
        return 1
    ok = status == 200
    _emit_event(
        "seo.report_sent" if ok else "seo.report_failed",
        hours=args.hours, visits=stats.total, http_status=status,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
