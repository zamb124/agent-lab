"""
Ключи i18n, которые статический сканер t() не видит (динамика, toasts, дубликаты shell).

Используются в check_i18n_keys.find_unused и в scripts/clean_i18n_unused.py.
"""

from __future__ import annotations

import re

_SKIP_ROOT = frozenset({"misc"})

_SCAN_EXCLUDED_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"^shell\."),
    re.compile(r"\.toast\."),
    re.compile(r"^(terms|privacy)\.section_\d+"),
    re.compile(r"^privacy\.(title|updated|updated_at)$"),
    re.compile(r"^terms\.(title|updated|updated_at)$"),
    re.compile(r"^billing\.tariff_plans\."),
    re.compile(r"^billing\.status\."),
    re.compile(r"^landing\.faq\.slot"),
    re.compile(r"^landing\.header\."),
    re.compile(r"^frontend\.platform_billing_page\.(tab_|system_access_role_)"),
    re.compile(r"^frontend\.settings_page\.provider_"),
    re.compile(r"^frontend\.team_roles\."),
    re.compile(r"^frontend\.embed_create_modal\."),
    re.compile(r"^crm\.graph\.(search_mode_|view_mode_)"),
    re.compile(r"^crm\.entities\.search_modes\."),
    re.compile(r"^crm\.entities_page\.status_"),
    re.compile(r"^crm\.entities\.status\."),
    re.compile(r"^crm\.access_requests_page\.(filter_|empty_|status_)"),
    re.compile(r"^crm\.settings_hub_page\."),
    re.compile(r"^crm\.entity_detail_page\.tab_"),
    re.compile(r"^crm\.sidebar\.nav\."),
    re.compile(r"^crm\.namespace_modal\.grants_(role_|subject_)"),
    re.compile(r"^crm\.share_modal\.(role_|subject_)"),
    re.compile(r"^crm\.knowledge_import_modal\."),
    re.compile(r"^crm\.entity_merge_modal\."),
    re.compile(r"^platform\.apps\."),
    re.compile(r"^platform\.file_preview_modal\."),
    re.compile(r"^flows\.http_resource_editor\.auth_"),
    re.compile(r"^flows\.rag_resource_editor\.provider_"),
    re.compile(r"^flows\.external_api_editor\.location_"),
    re.compile(r"^flows\.trigger_editor_modal\."),
    re.compile(r"^flows\.flow_create_modal\.preset_"),
    re.compile(r"^flows\.operator\.status_"),
    re.compile(r"^flows\.canvas\.context_menu\."),
    re.compile(r"^documents\.list\.docType\."),
)


def terminal_key_excluded_from_unused_report(fullkey: str) -> bool:
    root = fullkey.split(".", 1)[0]
    if root in _SKIP_ROOT:
        return True
    # sync: много ключей через динамические шаблоны и this.t('a.b') без префикса ns в скане.
    if root == "sync":
        return True
    return any(r.search(fullkey) for r in _SCAN_EXCLUDED_RES)


def terminal_key_protected_from_prune(fullkey: str) -> bool:
    """Те же правила, что и для отчёта unused (в т.ч. запрет prune sync)."""
    return terminal_key_excluded_from_unused_report(fullkey)
