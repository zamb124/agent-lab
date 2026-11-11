"""IndexNow: мгновенное уведомление Bing/Yandex о новых и изменённых URL.

Читает ключ из ``conf.json``/env (``frontend.indexnow_key`` / ``FRONTEND__INDEXNOW_KEY``);
при заданном ключе frontend также отдаёт ``https://<host>/<key>.txt`` для верификации.

CronJob ``seo-indexnow`` (``70-observability``) запускает сбор всех sitemap URL
и submit раз в 6 часов; финальная строка — машинная
``{"message": "seo.indexnow_ok|seo.indexnow_failed|seo.indexnow_skipped"}``
для Grafana-алерта ``seo-indexnow-failures``.

Запуск вручную:
    uv run python -m scripts.seo.index_now                 # все sitemap URL
    uv run python -m scripts.seo.index_now --url https://linnex.io/blog/new-post
    uv run python -m scripts.seo.index_now --dry-run       # показать payload, не слать
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx2

from apps.frontend.config import get_frontend_settings
from apps.frontend.seo.blog_files import read_blog_index
from apps.frontend.seo.pages import PUBLIC_PAGES, SEO_LOCALES, localized_marketing_path
from core.platform_brand.resolver import resolve_seo_base_url

REPO_ROOT = Path(__file__).resolve().parents[2]
# api.indexnow.org — федеративная точка (Bing и участники); yandex.ru —
# собственный приём Яндекса: для RU-выдачи сабмитим в обе.
INDEXNOW_ENDPOINTS = (
    "https://api.indexnow.org/indexnow",
    "https://yandex.ru/indexnow",
)
_LOC_RE = re.compile(r"<loc>(.*?)</loc>")


def _local_sitemap_urls() -> list[str]:
    """URL из локальных артефактов: sitemap маркетинга строится в рантайме — берём
    реестр страниц и файлы seo-dist/documentation-dist."""
    base = resolve_seo_base_url()
    urls: list[str] = []
    for page in PUBLIC_PAGES:
        for locale in SEO_LOCALES:
            localized = localized_marketing_path(page.path, locale)
            urls.append(f"{base}/{localized}" if localized else f"{base}/")
    for item in read_blog_index():
        slug = str(item["slug"])
        urls.append(f"{base}/blog/{slug}")
        if item.get("has_en"):
            urls.append(f"{base}/en/blog/{slug}")
    return urls


def _sitemap_urls_from_file(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except ET.ParseError:
        return _LOC_RE.findall(path.read_text(encoding="utf-8"))
    return [
        text
        for loc in root.iter()
        if loc.tag.endswith("loc")
        if (text := loc.text) is not None
    ]


def collect_urls() -> list[str]:
    urls = _local_sitemap_urls()
    for sitemap in (
        REPO_ROOT / "documentation-dist" / "sitemap.xml",
        REPO_ROOT / "documentation-dist" / "en" / "sitemap.xml",
    ):
        urls.extend(_sitemap_urls_from_file(sitemap))
    return sorted(set(urls))


def _indexnow_key() -> str | None:
    value = get_frontend_settings().indexnow_key
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _provider(endpoint: str) -> str:
    """Короткое имя провайдера по URL эндпоинта (для поля providers события)."""
    return endpoint.split("://", 1)[-1].split("/", 1)[0]


def submit(
    urls: list[str], *, key: str, dry_run: bool
) -> tuple[int, int | None, dict[str, int | None]]:
    base = resolve_seo_base_url()
    payload = {
        "host": base.removeprefix("https://").removeprefix("http://"),
        "key": key,
        "keyLocation": f"{base}/{key}.txt",
        "urlList": urls,
    }
    body = json.dumps(payload).encode("utf-8")
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])
        print(f"index_now dry-run: {len(urls)} urls")
        return 0, None, {}
    statuses: dict[str, int | None] = {}
    for endpoint in INDEXNOW_ENDPOINTS:
        provider = _provider(endpoint)
        try:
            response = httpx2.post(
                endpoint,
                content=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=30.0,
            )
        except httpx2.HTTPError as exc:
            statuses[provider] = None
            print(f"index_now: {len(urls)} urls → {endpoint} transport error: {exc}")
            continue
        statuses[provider] = response.status_code
        print(f"index_now: {len(urls)} urls → {endpoint} HTTP {response.status_code}")
    # IndexNow: 200/202 — принято; прочее (403 ключ, 422 payload) — провал.
    # Фейлом считается отказ хотя бы одного эндпоинта: RU-выдача зависит
    # от Яндекса, глобальная — от федеративного api.indexnow.org.
    ok = statuses and all(status in (200, 202) for status in statuses.values())
    worst = next(
        (status for status in statuses.values() if status not in (200, 202)),
        next(iter(statuses.values()), None),
    )
    return (0 if ok else 1), worst, statuses


def _emit_event(
    event: str,
    *,
    urls: int,
    http_status: int | None,
    providers: dict[str, int | None],
) -> None:
    """Машинная строка для Loki: CronJob seo-indexnow пишет её в stdout,
    Grafana-алерт ловит ``seo.indexnow_failed`` (``| json | message=``)."""
    print(json.dumps({
        "message": event,
        "level": "WARNING" if event.endswith("failed") else "INFO",
        "urls": urls,
        "http_status": http_status,
        "providers": providers,
    }, ensure_ascii=False))


@dataclasses.dataclass
class _Args:
    url: list[str] = dataclasses.field(default_factory=list)
    dry_run: bool = False


def main() -> int:
    parser = argparse.ArgumentParser(description="IndexNow submit")
    _ = parser.add_argument(
        "--url", action="append", default=[], help="конкретный URL (можно несколько)"
    )
    _ = parser.add_argument("--dry-run", action="store_true", help="не отправлять запрос")
    args = parser.parse_args(namespace=_Args())

    key = _indexnow_key()
    urls = args.url if args.url else collect_urls()
    if key is None:
        print("index_now: ключ не настроен (frontend.indexnow_key), список URL:")
        for url in urls[:20]:
            print(f"  {url}")
        print(f"... всего {len(urls)}; задайте ключ и повторите для отправки")
        _emit_event("seo.indexnow_skipped", urls=len(urls), http_status=None, providers={})
        return 0
    code, status, providers = submit(urls, key=key, dry_run=args.dry_run)
    if args.dry_run:
        return code
    _emit_event(
        "seo.indexnow_failed" if code else "seo.indexnow_ok",
        urls=len(urls),
        http_status=status,
        providers=providers,
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
