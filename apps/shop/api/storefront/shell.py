"""Storefront shell — HTML-страница витрины с inline-снапшотом.

Отдаётся анонимно на ``/s/{slug}``: снапшот из Redis встраивается в HTML
одним JSON-блоком, клиентский JS рендерит меню и корзину без SPA-сборки.
SSR-lite: первый байт уже содержит всё меню — SEO и скорость из коробки.

Шаблоны витрины (``theme.preset``): ``menu`` — классическое меню списком,
``grid`` — фотоплитка, ``compact`` — плотный список без фото.
"""

from __future__ import annotations

import json
from html import escape

from apps.shop.api.storefront.blocks import custom_injections, page_css, page_js
from apps.shop.api.storefront.blocks.account import account_tail
from core.platform_brand.resolver import (
    resolve_brand_apex_origin,
    resolve_brand_or_primary,
    supported_domains,
)
from core.types import JsonObject
from core.utils.domain import (
    extract_base_domain,
    get_protocol,
    is_local,
    split_host_port,
)

_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{description}">
<meta name="theme-color" content="{accent}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<script>{platform_brand}</script>
<script type="module" src="/static/core/lib/customer-auth/autoload.js"></script>
{seo_head}
{pwa_head}
{custom_head}
<style>
:root{{--accent:{accent};--on-accent:{on_accent};--afg:{afg_dark};--bg:#131110;--card:#1e1a17;--card2:#2a241f;--text:#f7f3ec;--muted:#a39a8d;--line:#2e2823;--radius:18px;--overlay:rgba(10,9,8,.62);--on-hero:#fff;--success:#4ade80;--warn:#f0b45c;--shadow-sm:0 1px 2px rgba(0,0,0,.4);--shadow-lg:0 14px 44px rgba(0,0,0,.55);color-scheme:dark}}
body.light{{--bg:#f5f4f2;--card:#ffffff;--card2:#eeebe7;--text:#1d1a16;--muted:#6e665a;--line:#e5e1da;--overlay:rgba(24,20,15,.45);--success:#15803d;--warn:#b45309;--afg:{afg_light};--shadow-sm:0 1px 2px rgba(24,20,15,.07),0 2px 8px rgba(24,20,15,.05);--shadow-lg:0 16px 44px rgba(24,20,15,.16);color-scheme:light}}
{blocks_css}
{custom_css}
</style>
</head>
<body class="{body_class}" data-preset="{preset}" data-hero="{hero_style}" data-backdrop="{backdrop}">
{custom_top}
<div class="wrap" id="app"></div>
<button class="cart" id="cart" onclick="openSheet()"></button>
<div class="sheet" id="sheet" onclick="if(event.target===this)closeSheet()"><div class="panel"><div class="grab"></div><div id="panel"></div></div></div>
<div class="sheet" id="csheet" onclick="if(event.target===this)closeCust()"><div class="panel"><div class="grab"></div><div id="cpanel"></div></div></div>
<div class="toast" id="toast"></div>
<script id="snapshot" type="application/json">{snapshot}</script>
<script>
{blocks_js}
{custom_js}
</script>
{custom_bottom}
{account_tail}
</body>
</html>"""


_JSONLD_TYPES: dict[str, str] = {
    "restaurant": "Restaurant",
    "cafe": "CafeOrCoffeeShop",
    "bakery": "Bakery",
    "shop": "Store",
}
_DAYS: tuple[str, ...] = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")

_DEFAULT_ACCENT = "#e2553f"

_Rgb = tuple[int, int, int]
# Фоны тем из CSS — производные accent-токены считаются под конкретный фон.
_BG_DARK: _Rgb = (0x13, 0x11, 0x10)
_BG_LIGHT: _Rgb = (0xF5, 0xF4, 0xF2)
_TEXT_DARK: _Rgb = (0xF7, 0xF3, 0xEC)
_TEXT_LIGHT: _Rgb = (0x1D, 0x1A, 0x16)


def hex_rgb(value: str) -> _Rgb:
    """'#rgb'/'#rrggbb' → (r,g,b); невалидный ввод — rgb дефолтного accent."""
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    try:
        if len(s) != 6:
            raise ValueError(value)
        return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    except ValueError:
        return (0xE2, 0x55, 0x3F)


def rel_luminance(rgb: _Rgb) -> float:
    """Относительная яркость WCAG 2.x."""

    def lin(channel: int) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])


def contrast_ratio(a: _Rgb, b: _Rgb) -> float:
    hi = max(rel_luminance(a), rel_luminance(b))
    lo = min(rel_luminance(a), rel_luminance(b))
    return (hi + 0.05) / (lo + 0.05)


def to_hex(rgb: _Rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def mix_rgb(a: _Rgb, b: _Rgb, t: float) -> _Rgb:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def on_accent(accent: _Rgb) -> str:
    """Текст на accent-кнопке: белый, пока контраст ≥3; иначе тёмный."""
    return "#fff" if contrast_ratio(accent, (255, 255, 255)) >= 3.0 else "#1d1a16"


def accent_fg(accent: _Rgb, bg: _Rgb, text: _Rgb) -> str:
    """Accent для текста/иконок на фоне: доводится смесью к text до контраста 4.5."""
    for step in range(0, 21):
        cand = mix_rgb(accent, text, step / 20)
        if contrast_ratio(cand, bg) >= 4.5:
            return to_hex(cand)
    return to_hex(text)


def accent_vars(accent: str) -> dict[str, str]:
    """Производные токены accent для шаблона: --on-accent и --afg под каждую тему."""
    rgb = hex_rgb(accent)
    return {
        "on_accent": on_accent(rgb),
        "afg_dark": accent_fg(rgb, _BG_DARK, _TEXT_DARK),
        "afg_light": accent_fg(rgb, _BG_LIGHT, _TEXT_LIGHT),
    }


def _opening_hours(snapshot: JsonObject) -> list[JsonObject]:
    """working_hours {day: 'HH:MM-HH:MM'} → schema.org openingHoursSpecification."""
    raw = snapshot.get("working_hours")
    if not isinstance(raw, dict):
        return []
    specs: list[JsonObject] = []
    for day, hours in raw.items():
        if not isinstance(hours, str):
            continue
        if not day.isdigit() or not (0 <= int(day) <= 6) or "-" not in hours:
            continue
        opens, _, closes = hours.partition("-")
        specs.append(
            {
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": _DAYS[int(day)],
                "opens": opens.strip(),
                "closes": closes.strip(),
            }
        )
    return specs


def _menu_items(snapshot: JsonObject) -> list[JsonObject]:
    """Позиции каталога → hasMenu/hasMenuItem с offers для rich-результатов."""
    raw = snapshot.get("products")
    if not isinstance(raw, list):
        return []
    items: list[JsonObject] = []
    for product in raw[:50]:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str):
            continue
        item: JsonObject = {"@type": "MenuItem", "name": product["name"]}
        price = product.get("price_minor")
        currency = snapshot.get("currency")
        if isinstance(price, int) and price > 0 and isinstance(currency, str):
            item["offers"] = {
                "@type": "Offer",
                "price": f"{price / 100:.2f}",
                "priceCurrency": currency,
            }
        description = product.get("description")
        if isinstance(description, str) and description:
            item["description"] = description
        items.append(item)
    return items


def _storefront_jsonld(snapshot: JsonObject, canonical_url: str, image_url: str) -> JsonObject:
    """LocalBusiness-граф витрины: тип по kind, адрес, часы, меню."""
    kind = snapshot.get("kind")
    doc: JsonObject = {
        "@context": "https://schema.org",
        "@type": _JSONLD_TYPES.get(str(kind), "LocalBusiness"),
        "name": snapshot.get("name", ""),
        "url": canonical_url,
    }
    description = snapshot.get("description")
    if isinstance(description, str) and description:
        doc["description"] = description
    if image_url:
        doc["image"] = image_url
    phone = snapshot.get("phone")
    if isinstance(phone, str) and phone:
        doc["telephone"] = phone
    city = snapshot.get("city")
    address = snapshot.get("address")
    if (isinstance(city, str) and city) or (isinstance(address, str) and address):
        doc["address"] = {
            "@type": "PostalAddress",
            **({"addressLocality": city} if isinstance(city, str) and city else {}),
            **({"streetAddress": address} if isinstance(address, str) and address else {}),
        }
    specs = _opening_hours(snapshot)
    if specs:
        doc["openingHoursSpecification"] = specs
    items = _menu_items(snapshot)
    if items:
        doc["hasMenu"] = {"@type": "Menu", "hasMenuItem": items}
    return doc


def _seo_head(
    *,
    title: str,
    description: str,
    canonical_url: str,
    image_url: str,
    jsonld: JsonObject,
) -> str:
    """OG/Twitter мета + canonical + JSON-LD — шаринг и rich snippets."""
    tags = [
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{escape(title)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        '<meta property="og:locale" content="ru_RU">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
    if canonical_url:
        tags.append(f'<link rel="canonical" href="{escape(canonical_url)}">')
        tags.append(f'<meta property="og:url" content="{escape(canonical_url)}">')
    if image_url:
        tags.append(f'<meta property="og:image" content="{escape(image_url)}">')
    ld = json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/")
    tags.append(f'<script type="application/ld+json">{ld}</script>')
    return "\n".join(tags)


def _platform_brand_bootstrap(host: str) -> JsonObject:
    """``window.__PLATFORM_BRAND__`` для embed-компонентов на витринной странице.

    Тот же контракт, что у PlatformApp (`/frontend/api/platform/brand` →
    `window.__PLATFORM_BRAND__`): `<platform-map>`, `<platform-customer-auth>`
    и прочие PlatformElement-embed'ы читают бренд для i18n-интерполяции.
    Названия бренда — из `platform_brands` конфигурации по Host запроса.
    """
    brand = resolve_brand_or_primary(host or None)
    hostname, port = split_host_port(host) if host else ("", None)
    protocol = get_protocol(host) if host else "https"
    try:
        base_domain = extract_base_domain(host) if host else ""
    except ValueError:
        base_domain = ""
    if not base_domain:
        base_domain = hostname or "localhost"
    try:
        apex_origin = resolve_brand_apex_origin(host, url_scheme=protocol)
    except ValueError:
        apex_origin = f"{protocol}://{hostname}/" if hostname else "/"
    return {
        "isProduction": not is_local(host),
        "baseDomain": base_domain,
        "portSuffix": f":{port}" if port else "",
        "protocol": protocol,
        "platformName": brand.platform_name,
        "supportEmail": brand.support_email,
        "logoPath": brand.logo_path,
        "apexOrigin": apex_origin,
        "supportedDomains": list(supported_domains()),
        "modelsProductName": brand.models_product_name,
        "voiceProductName": brand.voice_product_name,
        "llmsDisplayLabel": brand.llms_display_label,
        "flowsProductLabel": brand.flows_product_label,
    }


def storefront_html(
    snapshot: JsonObject,
    *,
    canonical_url: str = "",
    image_url: str = "",
    host: str = "",
) -> str:
    """HTML витрины с inline-снапшотом для SSR-lite рендера."""
    accent = _DEFAULT_ACCENT
    preset = "menu"
    mode = "dark"
    hero_style = "card"
    backdrop = "solid"
    theme = snapshot.get("theme")
    if isinstance(theme, dict):
        accent = str(theme.get("accent_color", accent))
        preset = str(theme.get("preset", preset))
        mode = str(theme.get("mode", mode))
        hero_style = str(theme.get("hero_style", hero_style))
        backdrop = str(theme.get("backdrop", backdrop))
    tokens = accent_vars(accent)
    body_class = " ".join(
        part
        for part in (
            "compact" if preset == "compact" else "",
            "light" if mode == "light" else "",
        )
        if part
    )
    title = str(snapshot.get("name", "Витрина"))
    description = str(snapshot.get("description", ""))[:200]
    slug = str(snapshot.get("slug", ""))
    pwa_head = "\n".join(
        [
            '<meta name="mobile-web-app-capable" content="yes">',
            f'<link rel="icon" type="image/svg+xml" href="/shop/api/v1/public/storefront/{escape(slug)}/icon.svg">' if slug else "",
            f'<link rel="manifest" href="/shop/api/v1/public/storefront/{escape(slug)}/manifest.webmanifest">' if slug else "",
        ]
    )
    return _PAGE.format(
        platform_brand="window.__PLATFORM_BRAND__="
        + json.dumps(_platform_brand_bootstrap(host), ensure_ascii=False)
        .replace("</", "<\\/"),
        title=escape(title),
        description=escape(description),
        seo_head=_seo_head(
            title=title,
            description=description,
            canonical_url=canonical_url,
            image_url=image_url,
            jsonld=_storefront_jsonld(snapshot, canonical_url, image_url),
        ),
        accent=escape(accent),
        on_accent=tokens["on_accent"],
        afg_dark=tokens["afg_dark"],
        afg_light=tokens["afg_light"],
        body_class=escape(body_class),
        preset=escape(preset),
        hero_style=escape(hero_style),
        backdrop=escape(backdrop),
        snapshot=json.dumps(snapshot, ensure_ascii=False).replace("</", "<\\/"),
        pwa_head=pwa_head,
        blocks_css=page_css(),
        blocks_js=page_js(),
        account_tail=account_tail(),
        **custom_injections(snapshot),
    )
