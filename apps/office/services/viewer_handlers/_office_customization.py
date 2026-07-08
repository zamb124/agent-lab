"""OnlyOffice editor customization payload (вынесено из BFF)."""

from __future__ import annotations

from urllib.parse import urlparse

from apps.office.config import get_office_settings
from core.platform_brand.resolver import (
    resolve_brand,
    resolve_context_host,
    resolve_public_base_url,
)
from core.types import JsonObject


def _editor_header_brand_base_url(*, brand_host: str | None = None) -> str:
    settings = get_office_settings()
    ec = settings.office.editor_customization
    manual = ec.branding_public_base_url.strip().rstrip("/")
    if manual:
        return manual
    if brand_host is not None and str(brand_host).strip():
        return resolve_public_base_url(str(brand_host).strip()).rstrip("/")
    context_host = resolve_context_host()
    if context_host is not None:
        return resolve_public_base_url(context_host).rstrip("/")
    if brand_host is not None and str(brand_host).strip():
        return resolve_public_base_url(str(brand_host).strip()).rstrip("/")
    raise ValueError(
        "office editor branding requires brand_host or request context host"
    )


def onlyoffice_editor_customization_payload(*, brand_host: str | None = None) -> JsonObject:
    settings = get_office_settings()
    ec = settings.office.editor_customization
    customization: JsonObject = {
        "compactToolbar": ec.compact_toolbar,
        "compactHeader": ec.compact_header,
        "uiTheme": ec.ui_theme,
        "features": {"featuresTips": ec.features_tips},
    }
    platform_name = "HUMANITEC"
    logo_path = "/static/core/assets/service_logos/frontend_logo.svg"
    if brand_host is not None and str(brand_host).strip():
        brand = resolve_brand(str(brand_host).strip())
        platform_name = brand.platform_name.upper()
        logo_path = brand.logo_path
    image = ec.logo_image_url.strip()
    link_explicit = ec.logo_link_url.strip()
    if image:
        logo: JsonObject = {"image": image}
        dark = ec.logo_image_dark_url.strip()
        if dark:
            logo["imageDark"] = dark
        logo["url"] = link_explicit if link_explicit else ""
        customization["logo"] = logo
    elif ec.platform_header_branding:
        origin = _editor_header_brand_base_url(brand_host=brand_host)
        if origin:
            static_logo = f"{origin}{logo_path}"
            customization["logo"] = {
                "image": static_logo,
                "imageDark": static_logo,
                "url": link_explicit if link_explicit else f"{origin}/documents",
            }
            parsed = urlparse(origin)
            www = parsed.netloc if parsed.netloc else origin
            customization["customer"] = {"name": platform_name, "www": www}
    return customization
