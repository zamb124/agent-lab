"""DevInterServiceProxy: сопоставление первого сегмента пути и имени процесса."""

from core.middleware.dev_inter_service_proxy import (
    _ONLYOFFICE_STATIC_SEGMENTS,
    _is_local_target_for_process,
    _is_onlyoffice_upstream_path,
    _rewrite_upstream_origin_text,
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
    assert _is_onlyoffice_upstream_path(
        "/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/sdkjs-plugins/marketplace/config.json",
    )
    assert _is_onlyoffice_upstream_path("/command")
    assert _is_onlyoffice_upstream_path("/downloadfile/8d2fd647b568478487cbef88f584a4e0_file_7d8dfbc8544d")
    assert _is_onlyoffice_upstream_path(
        "/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/doc/8d2fd647b568478487cbef88f584a4e0_file_7d8dfbc8544d/c/",
    )
    assert _is_onlyoffice_upstream_path("/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/fonts/040")
    assert _is_onlyoffice_upstream_path(
        "/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/dictionaries/en_US/en_US.aff",
    )
    assert _is_onlyoffice_upstream_path("/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/themes.json")
    assert _is_onlyoffice_upstream_path("/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/plugins.json")
    assert _is_onlyoffice_upstream_path(
        "/9.3.1-bb79ceaf8d8c551aeef3cfc7d89ea4d0/document_editor_service_worker.js",
    )
    assert not _is_onlyoffice_upstream_path("/documents/edit/x")
    assert _is_onlyoffice_upstream_path("/web-apps/apps/api/documents/api.js")


def test_onlyoffice_origin_rewrite_handles_loopback_and_ws_urls() -> None:
    payload = (
        "http://localhost:8088/cache/files/data/Editor.bin "
        "ws://localhost:8088/9.3.1-build/doc/session/c/ "
        "http:\\/\\/127.0.0.1:8088\\/cache\\/files\\/data\\/Editor.bin"
    )

    assert _rewrite_upstream_origin_text(
        payload,
        upstream_origin="http://127.0.0.1:8088",
        public_origin="http://localhost:8002",
    ) == (
        "http://localhost:8002/cache/files/data/Editor.bin "
        "ws://localhost:8002/9.3.1-build/doc/session/c/ "
        "http:\\/\\/localhost:8002\\/cache\\/files\\/data\\/Editor.bin"
    )
