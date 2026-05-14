"""DevInterServiceProxy: сопоставление первого сегмента пути и имени процесса."""

from core.middleware.dev_inter_service_proxy import (
    _ONLYOFFICE_STATIC_SEGMENTS,
    _is_local_target_for_process,
    _is_onlyoffice_upstream_path,
)


def test_office_process_handles_documents_prefix() -> None:
    assert _is_local_target_for_process("documents", "office") is True


def test_frontend_process_proxies_documents() -> None:
    assert _is_local_target_for_process("documents", "frontend") is False


def test_flows_skips_only_own_segment() -> None:
    assert _is_local_target_for_process("flows", "flows") is True
    assert _is_local_target_for_process("documents", "flows") is False


def test_onlyoffice_static_segments() -> None:
    assert "web-apps" in _ONLYOFFICE_STATIC_SEGMENTS
    assert "common" in _ONLYOFFICE_STATIC_SEGMENTS
    assert "documents" not in _ONLYOFFICE_STATIC_SEGMENTS


def test_onlyoffice_versioned_web_apps_path() -> None:
    assert _is_onlyoffice_upstream_path(
        "/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/web-apps/apps/common/index.html",
    )
    assert _is_onlyoffice_upstream_path(
        "/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/sdkjs/common/AllFonts.js",
    )
    assert _is_onlyoffice_upstream_path("/downloadfile/8d2fd647b568478487cbef88f584a4e0_file_7d8dfbc8544d")
    assert _is_onlyoffice_upstream_path(
        "/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/doc/8d2fd647b568478487cbef88f584a4e0_file_7d8dfbc8544d/c/",
    )
    assert _is_onlyoffice_upstream_path("/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/fonts/040")
    assert not _is_onlyoffice_upstream_path("/documents/edit/x")
    assert _is_onlyoffice_upstream_path("/web-apps/apps/api/documents/api.js")
