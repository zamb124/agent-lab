#!/usr/bin/env python3
"""Проверяет наличие ключевых HumanitecAgent E2E тестов."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FUNCTIONS: dict[Path, tuple[str, ...]] = {
    REPO_ROOT / "tests/agent/e2e/test_agent_platform_mcp_e2e.py": (
        "test_e2e_platform_mcp_discover",
        "test_e2e_platform_mcp_tools_list_contains_flow",
        "test_e2e_platform_mcp_tools_call_success",
        "test_e2e_platform_mcp_device_mcp_offline",
        "test_e2e_platform_mcp_device_mcp_success",
        "test_e2e_platform_mcp_device_mcp_missing_params",
        "test_e2e_platform_mcp_context_id_continuity",
        "test_e2e_platform_mcp_audit_events",
    ),
    REPO_ROOT / "tests/agent/e2e/test_agent_platform_mcp_flows_e2e.py": (
        "test_mcp_flow_interrupt_and_resume",
        "test_mcp_flow_handoff_parent_child",
        "test_mcp_flow_tool_calculator",
        "test_mcp_flow_two_flows_mapping",
        "test_mcp_parallel_tools_call",
        "test_mcp_flow_taskiq_worker_down",
    ),
    REPO_ROOT / "tests/agent/e2e/test_agent_platform_mcp_impossible_e2e.py": (
        "test_imp_platform_mcp_other_company_flow",
        "test_imp_device_mcp_foreign_device_id",
        "test_imp_platform_mcp_invalid_json",
        "test_imp_platform_mcp_device_mcp_via_tools_call",
        "test_imp_register_wrong_pairing_code",
        "test_imp_platform_mcp_tools_list_without_auth",
        "test_imp_platform_mcp_revoked_device_jwt_returns_401",
    ),
    REPO_ROOT / "tests/flows/api/test_agent_platform_mcp.py": (
        "test_platform_mcp_tools_call_bad_tool_name",
    ),
    REPO_ROOT / "tests/ui/e2e/test_frontend_settings_agent.py": (
        "test_f1_settings_agent_tab_visible",
        "test_f2_settings_agent_connect_section",
        "test_f3_settings_agent_devices_empty",
        "test_f4_settings_agent_audit_empty",
        "test_f5_settings_agent_pairing_code",
        "test_f6_settings_agent_download_link",
        "test_f7_settings_agent_release_banner",
        "test_f8_settings_agent_help_text",
        "test_f9_settings_agent_devices_after_pair",
        "test_f10_settings_agent_revoke_device",
        "test_f11_settings_agent_policy_shell_toggle",
        "test_f12_settings_agent_audit_after_register",
        "test_f13_settings_agent_download_href",
        "test_f14_settings_agent_release_banner_lvh_origin",
        "test_f15_settings_agent_pairing_code_ttl",
    ),
    REPO_ROOT / "tests/agent/e2e/test_agent_llm_proxy_e2e.py": (
        "test_e2e_llm_proxy_models_list_auto",
        "test_e2e_llm_proxy_chat_completions",
        "test_e2e_llm_proxy_requires_device_bearer",
        "test_e2e_llm_proxy_revoked_device_returns_401",
    ),
    REPO_ROOT / "tests/agent/e2e/test_agent_register_with_auth_e2e.py": (
        "test_e2e_discover_includes_llm_api_url",
        "test_e2e_register_with_auth_returns_llm_bundle",
        "test_e2e_register_with_auth_unauthorized",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_download.py": (
        "test_d1_download_redirect",
        "test_d_discover_url_bundle",
        "test_d2_releases_status_checksums",
        "test_d3_release_artifact_installed",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_auth_pairing.py": (
        "test_d5_auth_device_token_deep_link",
        "test_d6_pairing_deep_link_playwright",
        "test_d7_manual_pairing_ui",
        "test_d12_device_mcp_roundtrip",
        "test_d13_revoke_mid_session_tunnel_closed",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_electron.py": (
        "test_d4_first_launch_electron_smoke",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_golden_path.py": (
        "test_d5_register_url_bundle",
        "test_d8_tunnel_online_after_register",
        "test_d9_tunnel_policy_frame",
        "test_d10_platform_mcp_tools_list",
        "test_d11_platform_mcp_tools_call",
        "test_d15_device_mcp_offline",
        "test_d_gold_pairing_tunnel_mcp_audit",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_goose_extensions.py": (
        "test_goose_dev_01_list_directory",
        "test_goose_dev_02_write_read_file_roundtrip",
        "test_goose_dev_03_get_file_info",
        "test_goose_dev_04_search_files",
        "test_goose_dev_05_run_command",
        "test_goose_dev_06_edit_file",
        "test_goose_dev_07_read_image",
        "test_goose_mem_01_store_retrieve_memory",
        "test_goose_mem_02_list_delete_memory",
        "test_goose_cc_01_computercontroller_tools_list",
        "test_goose_av_01_autovisualiser_tools_list",
        "test_goose_tut_01_tutorial_tools_list",
        "test_goose_ext_01_bundled_order_persisted_after_restart",
        "test_goose_ext_02_disable_developer_removes_tree_tool",
        "test_goose_ext_03_enable_disable_extension_toggle",
        "test_goose_ipc_01_humanitec_agent_status_paired",
        "test_goose_ipc_02_resync_extensions_after_pair",
        "test_goose_ipc_03_get_goosed_host_port_localhost",
        "test_goose_ipc_04_discover_urls_match_frontend",
        "test_goose_ipc_05_logout_clears_credentials",
        "test_goose_ipc_06_open_pairing_window",
        "test_goose_ipc_07_platform_mcp_env_updated_after_pair",
        "test_goose_ipc_08_llm_autoconfig_after_pair",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_goose_cc_av_tut.py": (
        "test_goose_cc_02_web_scrape",
        "test_goose_cc_03_cache_list",
        "test_goose_cc_04_pdf_tool",
        "test_goose_cc_05_docx_tool",
        "test_goose_cc_06_xlsx_tool",
        "test_goose_cc_07_automation_script",
        "test_goose_cc_08_computer_control",
        "test_goose_av_02_render_sankey",
        "test_goose_av_03_render_radar",
        "test_goose_av_04_render_donut",
        "test_goose_av_05_render_treemap",
        "test_goose_av_06_render_chord",
        "test_goose_av_07_render_map",
        "test_goose_av_08_render_mermaid",
        "test_goose_av_09_show_chart",
        "test_goose_tut_02_load_build_mcp_extension",
        "test_goose_tut_03_load_first_game",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_goose_platform_ext.py": (
        "test_goose_plat_01_analyze_directory",
        "test_goose_plat_02_todo_write",
        "test_goose_plat_03_apps_list",
        "test_goose_plat_08_chatrecall_tools_list",
        "test_goose_plat_09_extensionmanager_search",
        "test_goose_plat_11_summon_load",
        "test_goose_plat_13_summarize_tools_list",
        "test_goose_plat_14_skills_tools_list",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_goosed_config.py": (
        "test_goose_cfg_01_config_extensions_platform_mcp_first",
        "test_goose_cfg_02_disable_developer_reflected_in_tools",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_mcp_ui.py": (
        "test_mcp_bld_01_bundled_extensions_platform_mcp_first",
        "test_mcp_ui_01_first_launch_bundled_order",
        "test_mcp_ui_03_chat_mcp_picker_order",
        "test_mcp_ui_04_flow_tools_visible_via_platform_mcp",
        "test_mcp_ui_05_post_revoke_credentials_cleared",
        "test_mcp_g_01_empty_chat_picker_platform_mcp_first",
        "test_mcp_g_02_flow_description_in_tools_list",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_acceptance.py": (
        "test_mcp_g_int_chat_interrupt_resume",
        "test_mcp_g_04_two_flows_in_session",
        "test_mcp_g_05_failed_flow_in_chat",
        "test_acc_01_settings_extensions_order_after_pair",
        "test_acc_02_settings_picker_interrupt_flow",
        "test_acc_03_discover_download_matches_local_release",
        "test_acc_04_audit_after_platform_mcp_call",
        "test_acc_05_in_flight_revoke_tunnel_offline",
        "test_acc_06_second_device_in_list",
        "test_acc_07_policy_toggle_via_api",
        "test_acc_08_golden_pair_mcp_picker_interrupt",
        "test_acc_09_no_goose_provider_onboarding",
    ),
    REPO_ROOT / "tests/agent/desktop_e2e/test_agent_desktop_mcp_flows.py": (
        "test_d_flow_03_desktop_mcp_interrupt_resume",
        "test_mcp_g_03_chat_select_platform_mcp_flow_tool",
        "test_d11_local_mcp_url_proxy_via_device_mcp",
        "test_d12_device_mcp_audit",
    ),
    REPO_ROOT / "tests/agent/e2e/test_agent_tunnel_multipod_e2e.py": (
        "test_e2e_multipod_platform_mcp_device_mcp_http",
    ),
    REPO_ROOT / "tests/agent/test_agent_release_status.py": (
        "test_release_status_draft_not_ready",
        "test_release_status_empty_assets_not_ready",
        "test_release_status_ready_with_checksums",
    ),
}


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            names.add(node.name)
    return names


def main() -> int:
    missing: list[str] = []
    for path, required in REQUIRED_FUNCTIONS.items():
        if not path.is_file():
            missing.append(f"missing file: {path.relative_to(REPO_ROOT)}")
            continue
        present = _function_names(path)
        for function_name in required:
            if function_name not in present:
                missing.append(f"{path.relative_to(REPO_ROOT)}::{function_name}")
    if missing:
        print("check_agent_e2e_coverage: missing tests:", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("check_agent_e2e_coverage: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
