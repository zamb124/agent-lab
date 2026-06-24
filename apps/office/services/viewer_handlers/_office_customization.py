"""OnlyOffice editor customization payload (вынесено из BFF)."""

from __future__ import annotations

from urllib.parse import urlparse

from apps.office.config import get_office_settings
from core.types import JsonObject

_HUMANITEC_PLATFORM_LOGO_PATH = "/static/core/assets/service_logos/frontend_logo.svg"


def _editor_header_brand_base_url() -> str:
    settings = get_office_settings()
    ec = settings.office.editor_customization
    manual = ec.branding_public_base_url.strip().rstrip("/")
    if manual:
        return manual
    srv = settings.server
    for candidate in (srv.platform_public_base_url, srv.frontend_service_url, srv.office_service_url):
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip().rstrip("/")
    return ""


def onlyoffice_editor_customization_payload() -> JsonObject:
    settings = get_office_settings()
    ec = settings.office.editor_customization
    customization: JsonObject = {
        "compactToolbar": ec.compact_toolbar,
        "compactHeader": ec.compact_header,
        "uiTheme": ec.ui_theme,
        "features": {"featuresTips": ec.features_tips},
    }
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
        origin = _editor_header_brand_base_url()
        if origin:
            static_logo = f"{origin}{_HUMANITEC_PLATFORM_LOGO_PATH}"
            customization["logo"] = {
                "image": static_logo,
                "imageDark": static_logo,
                "url": link_explicit if link_explicit else f"{origin}/documents",
            }
            parsed = urlparse(origin)
            www = parsed.netloc if parsed.netloc else origin
            customization["customer"] = {"name": "HUMANITEC", "www": www}
    return customization
