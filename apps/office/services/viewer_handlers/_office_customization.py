"""OnlyOffice editor customization payload (CE standard branding)."""

from __future__ import annotations

from apps.office.config import get_office_settings
from core.types import JsonObject


def onlyoffice_editor_customization_payload() -> JsonObject:
    """CE-safe editorConfig.customization: theme, compact chrome, underline tabs.

    Developer-only fields (logo, customer, white-label layout) are intentionally
    omitted — Community Edition ignores them and LICENSE §7 requires the
    ONLYOFFICE product logo to remain visible.
    """
    ec = get_office_settings().office.editor_customization
    return {
        "compactToolbar": ec.compact_toolbar,
        "compactHeader": ec.compact_header,
        "uiTheme": ec.ui_theme,
        "features": {
            "featuresTips": ec.features_tips,
            "tabStyle": {"mode": ec.tab_style, "change": False},
            "tabBackground": {"mode": ec.tab_background, "change": False},
        },
    }
