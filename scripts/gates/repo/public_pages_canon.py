#!/usr/bin/env python3
"""CI gate: паритет публичных индексируемых страниц.

Инварианты:
1. Каждый ``PublicPage.path`` в ``apps/frontend/seo/pages.py`` имеет маршрут
   в ``FRONTEND_ROUTES`` (apps/frontend/ui/app/frontend-app.ts).
2. Каждый публичный маршрут лендинга (``LANDING_ROUTE_KEYS``, без параметров)
   присутствует в ``PUBLIC_PAGES`` — новая маркетинговая страница без записи
   в реестре не попадёт в sitemap/llms/снапшоты.
3. Каждый путь ``PUBLIC_PAGES`` покрыт анонимным ``RouteRule`` в
   ``core/middleware/auth/route_config.py`` — иначе краулер упрётся в auth.
4. ``/en`` и ``/en/*`` — анонимные правила (английское зеркало).
5. ``PublicPage.route_key`` существует в ``FRONTEND_ROUTES`` и его path
   совпадает с ``PublicPage.path`` — опечатка в ключе ломает паритет.
6. ``routes.<route_key>`` есть в ``frontend.json`` обеих локалей — JSON-LD
   берёт оттуда nav-тайтлы breadcrumb.
7. ``products/<key>`` страницы имеют запись ``<key>`` в
   ``frontend_products.json`` обеих локалей с ``meta_title``/``meta_description``
   — JSON-LD SoftwareApplication.
"""

from __future__ import annotations

import json
import re
import sys

from scripts.gates.kit import REPO_ROOT, report

FRONTEND_APP_TS = REPO_ROOT / "apps" / "frontend" / "ui" / "app" / "frontend-app.ts"
ROUTE_CONFIG = REPO_ROOT / "core" / "middleware" / "auth" / "route_config.py"
TRANSLATIONS = REPO_ROOT / "core" / "i18n" / "translations"

_ROUTE_PATH_RE = re.compile(r"\{\s*key:\s*'([^']+)'[^}]*path:\s*'([^']*)'")
_LANDING_KEYS_BLOCK_RE = re.compile(r"LANDING_ROUTE_KEYS\s*=\s*new Set\(\[([^\]]+)\]", re.DOTALL)
_ROUTE_RULE_RE = re.compile(r'RouteRule\("([^"]+)"[^)]*auth_required=False')
_KEY_RE = re.compile(r"'([^']+)'")


def _spa_routes() -> dict[str, str]:
    text = FRONTEND_APP_TS.read_text(encoding="utf-8")
    matches: list[tuple[str, str]] = _ROUTE_PATH_RE.findall(text)
    return {key: path for key, path in matches}


def _landing_route_paths(routes: dict[str, str]) -> set[str]:
    text = FRONTEND_APP_TS.read_text(encoding="utf-8")
    block = _LANDING_KEYS_BLOCK_RE.search(text)
    if block is None:
        raise RuntimeError("frontend-app.ts: не найден LANDING_ROUTE_KEYS")
    key_list: list[str] = _KEY_RE.findall(block.group(1))
    keys = set(key_list)
    return {routes[key] for key in keys if key in routes and ":" not in routes[key]}


def _anonymous_patterns() -> list[str]:
    text = ROUTE_CONFIG.read_text(encoding="utf-8")
    found: list[str] = _ROUTE_RULE_RE.findall(text)
    return found


def _i18n_bundle(locale: str, namespace: str) -> dict[str, object]:
    path = TRANSLATIONS / locale / f"{namespace}.json"
    if not path.is_file():
        raise RuntimeError(f"нет i18n-бандла {path}")
    data: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"i18n-бандл {path} — не объект")
    return {str(k): v for k, v in data.items()}


def _covered(path: str, patterns: list[str]) -> bool:
    """Путь ``a/b`` покрыт правилом ``/a/b`` или ``/a/*`` (префикс-глоб)."""
    target = "/" + path.strip("/")
    for pattern in patterns:
        if pattern.endswith("*"):
            if target.startswith(pattern[:-1]):
                return True
        elif target == pattern or target == pattern.rstrip("/"):
            return True
    return False


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from apps.frontend.seo.pages import PUBLIC_PAGES

    errors: list[str] = []
    routes = _spa_routes()
    spa_paths = set(routes.values())
    public_paths = {page.path for page in PUBLIC_PAGES}
    landing_paths = _landing_route_paths(routes)
    patterns = _anonymous_patterns()

    route_bundles = {loc: _i18n_bundle(loc, "frontend") for loc in ("ru", "en")}
    product_bundles = {loc: _i18n_bundle(loc, "frontend_products") for loc in ("ru", "en")}

    for page in PUBLIC_PAGES:
        if page.path and page.path not in spa_paths:
            errors.append(f"public page '{page.path}' без маршрута в FRONTEND_ROUTES")
        if not _covered(page.path, patterns):
            errors.append(f"public page '{page.path}' не покрыт анонимным RouteRule")
        spa_path = routes.get(page.route_key)
        if spa_path is None:
            errors.append(f"route_key '{page.route_key}' ('{page.path}') нет в FRONTEND_ROUTES")
        elif spa_path != page.path:
            errors.append(
                f"route_key '{page.route_key}' ведёт на '{spa_path}', а не '{page.path}'"
            )
        for loc in ("ru", "en"):
            routes_obj = route_bundles[loc].get("routes")
            if not isinstance(routes_obj, dict) or page.route_key not in routes_obj:
                errors.append(f"routes.{page.route_key} нет в frontend.json ({loc})")
            if page.kind == "product":
                product_key = page.path.rsplit("/", 1)[-1]
                product = product_bundles[loc].get(product_key)
                missing = not isinstance(product, dict) or any(
                    not product.get(k) for k in ("meta_title", "meta_description")
                )
                if missing:
                    errors.append(
                        f"frontend_products.{product_key} без meta_title/meta_description ({loc})"
                    )

    for path in sorted(landing_paths):
        if path not in public_paths:
            errors.append(f"LANDING маршрут '{path}' отсутствует в PUBLIC_PAGES (seo/pages.py)")

    for rule in ("/en", "/en/*"):
        if rule not in patterns:
            errors.append(f"нет анонимного RouteRule '{rule}' для английского зеркала")

    return report("check_public_pages_canon", errors)


if __name__ == "__main__":
    sys.exit(main())
