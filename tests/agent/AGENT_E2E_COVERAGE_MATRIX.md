# HumanitecAgent E2E Coverage Matrix

Канонический список сценариев и привязка к pytest. CI gate: `scripts/check_agent_e2e_coverage.py` + `scripts/check_agent_goose_tool_contract.py`.

## Platform MCP (HTTP)

| ID | Test | File |
|---|---|---|
| PMCP-01 | `test_e2e_platform_mcp_discover` | `tests/agent/e2e/test_agent_platform_mcp_e2e.py` |
| PMCP-02 | `test_e2e_platform_mcp_tools_list_contains_flow` | same |
| PMCP-03 | `test_e2e_platform_mcp_tools_call_success` | same |
| PMCP-04 | `test_e2e_platform_mcp_device_mcp_offline` | same |
| PMCP-05 | `test_e2e_platform_mcp_device_mcp_success` | same |
| PMCP-06 | `test_e2e_platform_mcp_context_id_continuity` | same |
| PMCP-07 | `test_e2e_platform_mcp_audit_events` | same |

## Desktop golden path

| ID | Test | File |
|---|---|---|
| D-01..D-15 | download, pairing, tunnel, MCP, audit | `tests/agent/desktop_e2e/test_agent_desktop_*.py` |
| D-11 | `test_d11_local_mcp_url_proxy_via_device_mcp` | `test_agent_desktop_mcp_flows.py` (fixture `local_mcp_http_url` из `mcp_modes_stub`) |

## Goose extensions (goosed HTTP)

| ID | Test | File |
|---|---|---|
| GOOSE-DEV-01..07 | developer tools | `test_agent_desktop_goose_extensions.py` |
| GOOSE-MEM-01..02 | memory tools | same |
| GOOSE-CC-01..08 | computer controller | `test_agent_desktop_goose_extensions.py` + `test_agent_desktop_goose_cc_av_tut.py` |
| GOOSE-AV-01..09 | autovisualiser | same |
| GOOSE-TUT-01..03 | tutorial | same |
| GOOSE-EXT-01..03 | bundled order, disable developer, toggle | `test_agent_desktop_goose_extensions.py` |
| GOOSE-IPC-01..07 | Electron preload IPC | same |
| GOOSE-PLAT-01..14 | platform extensions | `test_agent_desktop_goose_platform_ext.py` |
| GOOSE-CFG-01..02 | `/config/extensions` | `test_agent_desktop_goosed_config.py` |

## MCP UI / chat picker

| ID | Test | File |
|---|---|---|
| MCP-BLD-01..03 | bundled config contract | `test_agent_desktop_mcp_ui.py` |
| MCP-UI-01..06 | settings/chat picker | same |
| MCP-G-01 | `test_mcp_g_01_empty_chat_picker_platform_mcp_first` | same |
| MCP-G-02 | `test_mcp_g_02_flow_description_in_tools_list` | same |
| MCP-G-03..05 | chat flow selection / interrupt | `test_agent_desktop_mcp_flows.py`, `test_agent_desktop_acceptance.py` |

## Acceptance (L4)

| ID | Test | File |
|---|---|---|
| ACC-01 | settings extensions order | `test_agent_desktop_acceptance.py` |
| ACC-02 | settings + picker + interrupt flow | same |
| ACC-03 | discover download ↔ settings | same |
| ACC-04 | audit after Platform MCP call | same |
| ACC-05 | in-flight revoke | same |
| ACC-06 | second device in list | same |
| ACC-07 | policy toggle via API | same |
| ACC-08 | golden pair + picker + interrupt | same |
| ACC-09 | no Goose provider onboarding after pair | same |

## LLM proxy (backend)

| ID | Test | File |
|---|---|---|
| LLM-01 | `test_e2e_llm_proxy_models_list_auto` | `tests/agent/e2e/test_agent_llm_proxy_e2e.py` |
| LLM-02 | `test_e2e_llm_proxy_chat_completions` | same |
| LLM-03 | revoked device → 401 | same |
| REG-AUTH-01 | `test_e2e_register_with_auth_returns_llm_bundle` | `tests/agent/e2e/test_agent_register_with_auth_e2e.py` |
| DES-LLM-01 | `test_goose_ipc_08_llm_autoconfig_after_pair` | `tests/agent/desktop_e2e/test_agent_desktop_goose_extensions.py` |

## Frontend settings (F-1..F-15)

| ID | Test | File |
|---|---|---|
| F-1..F-15 | `test_f1_settings_agent_tab_visible` … `test_f15_settings_agent_pairing_code_ttl` | `tests/ui/e2e/test_frontend_settings_agent.py` |

## GitHub releases (prod) / local artifact (TESTING)

| ID | Test | File |
|---|---|---|
| REL-UNIT | draft/empty/ready payload parsing | `tests/agent/test_agent_release_status.py` |
| REL-LOCAL | download/discover/status через `dist/` | `tests/agent/desktop_e2e/test_agent_desktop_download.py`, `tests/agent/e2e/test_agent_api_e2e.py` |

Precondition для TESTING: `AGENT__RELEASES__SOURCE=local` (default в `tests/conftest.py`) + `AGENT_ARTIFACT_MODE=release make agent-ensure`. GitHub token **не нужен**.

Production (`AGENT__RELEASES__SOURCE=github`): публичный GitHub Releases API без токена; token опционален для rate limit.
