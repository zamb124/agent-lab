"""SEO smoke-чеклист: публичная поверхность после деплоя.

Проверяет по живому базовому URL (по умолчанию canonical origin из conf.json):
- robots.txt: 200, sitemap-директива, allow публичного, disallow приватного;
- sitemap.xml: sitemapindex с дочерними картами; дочерние карты отдаются;
- llms.txt: 200, ссылки на документацию;
- маркетинговые страницы (RU + /en): 200, text/html, канонический <link canonical>
  на linnex.io, meta robots index, контент снапшота (не пустая оболочка);
- блог: /blog/feed.xml 200, первый пост 200 и содержит Article JSON-LD;
- приватные маршруты: X-Robots-Tag noindex или meta robots noindex;
- документация: /documentation/ 200, sitemap docs, llms.txt docs, .md зеркало;
- зеркала ``platform_brands`` (кроме dev-брендов): canonical на primary-домен.

Финальная строка — машинная ``{"message": "seo.smoke_ok|seo.smoke_failed"}``:
CronJob ``seo-synth`` (helm, */15м) пишет её в stdout → Loki → алерт
``seo-synth-failures``. Домен и зеркала — из ``scripts.seo.seo_config``.

Запуск:
    uv run python -m scripts.seo.seo_smoke                      # прод
    uv run python -m scripts.seo.seo_smoke --base http://localhost:8002
    uv run python -m scripts.seo.seo_smoke --host-header linnex.io --base http://127.0.0.1:8002
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys

import httpx2

from scripts.seo.seo_config import primary_platform_domain, public_mirror_domains, seo_base_url


class Check:
    def __init__(self) -> None:
        self.failed: int = 0
        self.passed: int = 0

    def ok(self, name: str, detail: str = "") -> None:
        self.passed += 1
        print(f"  OK   {name} {detail}")

    def fail(self, name: str, detail: str = "") -> None:
        self.failed += 1
        print(f"  FAIL {name} {detail}")


def _get(
    client: httpx2.Client, path: str, host_header: str | None
) -> tuple[int, httpx2.Headers, str]:
    """GET с кастомным Host; сетевая ошибка → ``(0, {}, "")`` — проверка фейлится."""
    headers: dict[str, str] = {}
    if host_header:
        headers["Host"] = host_header
    try:
        response = client.get(path, headers=headers or None)
    except httpx2.HTTPError:
        return 0, httpx2.Headers(), ""
    return response.status_code, response.headers, response.text


@dataclasses.dataclass
class _Args:
    base: str | None = None
    host_header: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description="SEO smoke checks")
    _ = parser.add_argument(
        "--base", default=None, help="базовый URL (default — canonical из conf.json)"
    )
    _ = parser.add_argument(
        "--host-header", default=None, help="Host header для проверки на IP/localhost"
    )
    args = parser.parse_args(namespace=_Args())
    base = (args.base if args.base is not None else seo_base_url()).rstrip("/")
    host_header = args.host_header
    canonical_host = primary_platform_domain()
    check = Check()
    client = httpx2.Client(
        base_url=base,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "User-Agent": "seo-smoke/1.0",
        },
        timeout=20.0,
        follow_redirects=True,
    )

    status, _h, body = _get(client, "/robots.txt", host_header)
    if status == 200 and "Sitemap:" in body:
        check.ok("robots.txt", "sitemap directive")
    else:
        check.fail("robots.txt", f"status={status}")
    for marker in ("Disallow: /api/", "Allow: /", "GPTBot", "ClaudeBot"):
        if marker in body:
            check.ok(f"robots {marker}")
        else:
            check.fail(f"robots {marker}")
    if f"Sitemap: https://{canonical_host}/sitemap.xml" in body:
        check.ok("robots sitemap → canonical")
    else:
        check.fail("robots sitemap → canonical", f"sitemap указывает не на {canonical_host}")

    status, _h, body = _get(client, "/sitemap.xml", host_header)
    if status == 200 and "sitemapindex" in body:
        check.ok("sitemap.xml index")
    else:
        check.fail("sitemap.xml index", f"status={status}")
    for child in ("/sitemap-marketing.xml", "/sitemap-blog.xml"):
        status, _h, body = _get(client, child, host_header)
        if status == 200 and "<urlset" in body:
            check.ok(f"sitemap {child}")
        else:
            check.fail(f"sitemap {child}", f"status={status}")

    status, _h, body = _get(client, "/llms.txt", host_header)
    if status == 200 and "documentation" in body:
        check.ok("llms.txt")
    else:
        check.fail("llms.txt", f"status={status}")

    pages = (
        ("/", "landing"),
        ("/products/agents", "product ru"),
        ("/products/rag", "product ru"),
        ("/en/products/agents", "product en"),
        ("/en", "landing en"),
        ("/support", "support"),
        ("/blog", "blog list"),
        ("/about", "about"),
        ("/policy", "policy"),
    )
    for path, name in pages:
        status, headers, body = _get(client, path, host_header)
        if status != 200:
            check.fail(f"page {name} {path}", f"status={status}")
            continue
        canonical = re.search(r'rel="canonical" href="([^"]+)"', body)
        if canonical is None or canonical_host not in canonical.group(1):
            check.fail(f"page {name} canonical", str(canonical))
            continue
        if "noindex" in body:
            check.fail(f"page {name} robots", "noindex on public page")
            continue
        # Снапшот: DSD-разметка shadow DOM и реальный контент, не пустая оболочка.
        if len(body) < 20_000:
            check.fail(f"page {name} size", f"{len(body)} bytes — похоже на пустую оболочку")
            continue
        if "shadowrootmode" not in body:
            check.fail(f"page {name} snapshot", "нет DSD-разметки — снапшот не отдался")
            continue
        check.ok(f"page {name}", canonical.group(1))

    status, _h, body = _get(client, "/blog/feed.xml", host_header)
    if status == 200 and "<rss" in body:
        check.ok("blog feed.xml")
    else:
        check.fail("blog feed.xml", f"status={status}")

    # Первый пост из feed: RU и EN версии отдаются со своими canonical.
    first_slug = ""
    slug_match = re.search(r"<link>[^<]*/blog/([a-z0-9-]+)</link>", body)
    if slug_match is not None:
        first_slug = slug_match.group(1)
    for post_path in (f"/blog/{first_slug}", f"/en/blog/{first_slug}"):
        if not first_slug:
            break
        status, _h, body = _get(client, post_path, host_header)
        if status != 200:
            check.fail(f"blog post {post_path}", f"status={status}")
            continue
        canonical = re.search(r'rel="canonical" href="([^"]+)"', body)
        if canonical is None or canonical.group(1) != f"https://{canonical_host}{post_path}":
            check.fail(f"blog post {post_path} canonical", str(canonical))
            continue
        if "BlogPosting" not in body:
            check.fail(f"blog post {post_path} ld", "нет BlogPosting JSON-LD")
            continue
        check.ok(f"blog post {post_path}")

    index_status, _h, _index_body = _get(client, "/api/public/site-bundle", host_header)
    if index_status == 200:
        check.ok("site-bundle api")
    else:
        check.fail("site-bundle api", f"status={index_status}")

    for path in ("/login", "/settings", "/dashboard"):
        status, headers, body = _get(client, path, host_header)
        robots_header = headers.get("X-Robots-Tag") or headers.get("x-robots-tag") or ""
        if "noindex" in robots_header or 'content="noindex' in body or "noindex,nofollow" in body:
            check.ok(f"noindex {path}")
        else:
            check.fail(f"noindex {path}", f"status={status} header={robots_header!r}")

    status, _h, body = _get(client, "/documentation/", host_header)
    if status == 200:
        check.ok("documentation index")
    else:
        check.fail("documentation index", f"status={status}")
    status, _h, body = _get(client, "/documentation/llms.txt", host_header)
    if status == 200:
        check.ok("docs llms.txt")
    else:
        check.fail("docs llms.txt", f"status={status}")
    status, _h, body = _get(client, "/documentation/quickstart/index.md", host_header)
    if status == 200 and len(body) > 200:
        check.ok("docs .md mirror")
    else:
        check.fail("docs .md mirror", f"status={status}")
    status, _h, body = _get(client, "/documentation/sitemap.xml", host_header)
    if status == 200 and "<lastmod>" in body:
        check.ok("docs sitemap lastmod")
    elif status == 200:
        check.fail("docs sitemap lastmod", "lastmod отсутствует")
    else:
        check.fail("docs sitemap", f"status={status}")

    # Зеркала (прочие домены platform_brands) — canonical на primary-домен.
    # Отдельный клиент на зеркальный origin; проверяем только если смоук
    # бежит по canonical-хосту (внутри кластера зеркало снаружи не резолвится).
    if canonical_host in base:
        for mirror_domain in public_mirror_domains():
            mirror_client = httpx2.Client(
                base_url=f"https://{mirror_domain}", timeout=20.0,
                follow_redirects=True,
            )
            status, _h, body = _get(mirror_client, "/products/agents", None)
            mirror_client.close()
            if status == 200:
                canonical = re.search(r'rel="canonical" href="([^"]+)"', body)
                if canonical and canonical_host in canonical.group(1):
                    check.ok(f"{mirror_domain} canonical → {canonical_host}")
                else:
                    check.fail(f"{mirror_domain} canonical", str(canonical))
            elif status:
                check.fail(mirror_domain, f"status={status}")

    client.close()
    print(f"\nseo_smoke: {check.passed} passed, {check.failed} failed")
    # Машинная строка для Loki: CronJob seo-synth пишет её в stdout,
    # Alloy разбирает | json, Grafana-алерт ловит seo.smoke_failed.
    event = "seo.smoke_failed" if check.failed else "seo.smoke_ok"
    print(json.dumps({
        "message": event,
        "level": "WARNING" if check.failed else "INFO",
        "failures": check.failed,
        "passed": check.passed,
        "base": base,
    }, ensure_ascii=False))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
