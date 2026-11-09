"""Канонический домен и имя платформы для сборочных SEO-скриптов.

Источник истины — ``conf.json`` (``primary_platform_domain`` +
``platform_brands[primary].platform_name``): те же значения, что рантайм
получает через ``core.platform_brand.resolver``. Docs-builder образ не
содержит ``core/``, поэтому скрипты читают conf.json напрямую.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _str_dict(value: object, field: str) -> dict[str, object]:
    """dict из conf.json с нормализацией ключей — isinstance(dict) дал бы Unknown."""
    if not isinstance(value, dict):
        raise ValueError(f"conf.json: нет {field}")
    return {str(k): v for k, v in value.items()}


@lru_cache(maxsize=1)
def _conf() -> dict[str, object]:
    path = REPO_ROOT / "conf.json"
    if not path.is_file():
        raise FileNotFoundError(f"нет conf.json: {path}")
    return _str_dict(json.loads(path.read_text(encoding="utf-8")), "conf.json")


def primary_platform_domain() -> str:
    domain = _conf().get("primary_platform_domain")
    if not isinstance(domain, str) or not domain.strip():
        raise ValueError("conf.json: нет primary_platform_domain")
    return domain.strip()


def seo_base_url() -> str:
    return f"https://{primary_platform_domain()}"


def public_mirror_domains() -> list[str]:
    """Домены-зеркала: ``platform_brands`` с ``public_site`` кроме primary
    (dev-бренды localhost/lvh.me без public_site отфильтровываются)."""
    brands = _str_dict(_conf().get("platform_brands"), "platform_brands")
    primary = primary_platform_domain()
    return [
        str(domain)
        for domain, brand in brands.items()
        if domain != primary
        and isinstance(brand, dict)
        and "public_site" in brand
    ]


def platform_name() -> str:
    brands = _str_dict(_conf().get("platform_brands"), "platform_brands")
    domain = primary_platform_domain()
    brand = _str_dict(brands.get(domain), f"бренда {domain}")
    name = brand.get("platform_name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("conf.json: нет platform_name у primary-бренда")
    return name.strip()
