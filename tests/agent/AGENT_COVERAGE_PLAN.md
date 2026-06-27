# HumanitecAgent — план полного покрытия Goose + Platform

Канон: **реальный HumanitecAgent (release DMG)**, **реальный goosed**, **реальный Electron/CDP**, **реальный Postgres/Redis/TaskIQ**, **реальный flows/frontend HTTP/WS**.  
Запрещено в `tests/agent/e2e` и `tests/agent/desktop_e2e`: `monkeypatch`, `unittest.mock`, `patch` (`scripts/check_agent_test_no_monkeypatch.py`).  
Единственный допустимый мок LLM — **MockLLM через Redis** (`mock_llm:responses:flows`), как во всей платформе.

Источники Goose (upstream): [aaif-goose/goose](https://github.com/aaif-goose/goose) — `crates/goose-mcp`, `ui/desktop/openapi.json`, `acp-meta.json`.

---

## 0. Текущий baseline (не дублировать)

| Слой | Тестов | Gate | Статус |
|---|---|---|---|
| Backend HTTP/WS E2E | ~78 | `tests/agent/e2e/` | **76 pass / 2 fail** (см. §8) |
| Desktop + goosed | ~96 | `tests/agent/desktop_e2e/` | **BLOCKER: missing provider** после LLM autoconfig |
| Unit/contract | ~19 | `tests/agent/test_*.py` | OK |
| Frontend settings UI | 15 | `tests/ui/e2e/test_frontend_settings_agent.py` | в phase 4 `make test` |
| Coverage matrix | — | `AGENT_E2E_COVERAGE_MATRIX.md` + `check_agent_e2e_coverage.py` | OK |
| Goose tool suffixes | — | `check_agent_goose_tool_contract.py` | OK (static) |

**`make test`** уже включает agent (phase 4 в `mk/test.mk`):
- phase 4a: `tests/agent/e2e` + API mirrors
- phase 4c: `tests/agent/desktop_e2e` + settings UI (`-n0`, timeout 900s, `agent-ensure release`)

Phase 1 unit intentionally **игнорирует** `tests/agent/desktop_e2e` (слишком долго для xdist).

---

## 1. Архитектура взаимодействий (что покрываем)

```
User → HumanitecAgent (Electron)
         ├─ ACP WS → goosed (local Rust agent)
         │     ├─ builtin MCP: developer, memory, computercontroller, autovisualiser, tutorial
         │     ├─ platform extensions: analyze, todo, apps, extensionmanager, summon, chatrecall, summarize, skills, code_execution, tom
         │     └─ HTTP: /agent/start|resume|tools|call_tool, /config/extensions
         ├─ Humanitec IPC → pairing, tunnel, platform MCP env
         └─ Chat UI → Platform LLM (humanitec/auto) + Platform MCP (flows)

Platform ←→ HumanitecAgent
         ├─ REST/WS: register, discover, tunnel, device policy, audit
         ├─ Platform MCP HTTP: flow_* tools, device/mcp proxy
         └─ LLM OpenAI proxy: /agent/llm/v1/models|chat/completions
```

Каждая стрелка = минимум один **real E2E** тест без эмуляторов.

---

## 2. Goose — полный инвентарь возможностей (upstream)

### 2.1 Bundled extensions (Humanitec `bundled-extensions.json`)

| Extension | Type | Humanitec default | MCP tools (suffix) | Покрытие |
|---|---|---|---|---|
| `platform_mcp` | streamable_http | ON, primary | dynamic `flow_{flow_id}` | PMCP-*, D-10/11, MCP-G-*, ACC-* |
| `developer` | builtin | ON | `tree`, `write`, `shell`, `edit`, `read_image` | GOOSE-DEV-01..07 |
| `computercontroller` | builtin | ON (distro) | `web_scrape`, `cache`, `pdf_tool`, `docx_tool`, `xlsx_tool`, `automation_script`, `computer_control` | GOOSE-CC-01..08 |
| `memory` | builtin | OFF | `remember_memory`, `retrieve_memories`, `remove_specific_memory`, `remove_memory_category` | GOOSE-MEM-01..02 |
| `autovisualiser` | builtin | OFF | 8× `render_*`, `show_chart` | GOOSE-AV-01..09 |
| `tutorial` | builtin | OFF | `load_tutorial` | GOOSE-TUT-01..03 |

**Gaps (bundled, не в contract):** upstream docs упоминают `text_editor`, `screen_capture`, `image_processor` у developer — **нет call-level E2E**.

### 2.2 Platform extensions (in-process goosed, не в JSON)

| Extension | Tools (из UI/tests upstream) | Покрытие | Gap |
|---|---|---|---|
| `analyze` | `analyze` | GOOSE-PLAT-01 | — |
| `todo` | `todo_write`, `todo_read`? | GOOSE-PLAT-02 (write only) | **todo_read** |
| `apps` | `list_apps`, create/update/delete/launch | GOOSE-PLAT-03 (list only) | **CRUD apps** |
| `extensionmanager` | `search_available_extensions`, `manage_extensions`, `list_resources`, `read_resource` | GOOSE-PLAT-09 (search) | **manage/resources** |
| `summon` | `load`, `delegate` | GOOSE-PLAT-11 (load) | **delegate** |
| `chatrecall` | session search/load | GOOSE-PLAT-08 (list only) | **call-level** |
| `summarize` | summarize tools | GOOSE-PLAT-13 (list only) | **call-level** |
| `skills` | `load_skill` (deprecated → summon) | GOOSE-PLAT-14 (presence) | deprecation path |
| `code_execution` | `execute_typescript`, `get_function_details` | — | **полный gap** |
| `tom` | env injection only | — | **gap** (если включаем) |

**Мatrix debt:** IDs GOOSE-PLAT-04..07, 10, 12 **не существуют** — удалить из matrix или реализовать.

### 2.3 goosed HTTP API (`openapi.json`)

| Endpoint | Покрыт E2E | Приоритет gap |
|---|---|---|
| `POST /agent/start` | yes | — |
| `POST /agent/resume` | yes | — |
| `GET /agent/tools` | yes | — |
| `POST /agent/call_tool` | yes (не в openapi, но real) | документировать контракт |
| `GET /config/extensions` | GOOSE-CFG-01 | — |
| `POST /agent/add_extension` | no | P2 |
| `POST /agent/remove_extension` | no | P2 |
| `POST /agent/restart\|stop` | no | P3 |
| `POST /agent/update_*` | no | P3 |
| `/config/providers*` | no | P2 (после LLM autoconfig) |
| `/recipes/*`, `/schedule/*` | no | P3 (out of scope Humanitec v1) |
| `/dictation/*`, `/local-inference/*` | no | P3 |

### 2.4 ACP (WebSocket) — chat path

| Surface | Покрытие | Gap |
|---|---|---|
| `defaults/read\|save` (humanitec/auto) | GOOSE-IPC-08, ACC-09 | — |
| `providers/custom/create` | indirect via onboarding | explicit ACP test |
| `config/extensions/*` | via UI + GOOSE-EXT | ACP direct |
| `tools/call` via chat stream | ACC-02, MCP-G-03 | billing span |
| `session/*` export/import | no | P3 |

### 2.5 Humanitec IPC (`window.humanitecAgent`)

| API | Test ID |
|---|---|
| discover, pair, status, logout | GOOSE-IPC-01..05, D-* |
| resyncExtensions, onPlatformMcpEnvUpdated | GOOSE-IPC-02, 07 |
| openPairing, openSettings, distro | GOOSE-IPC-06, F-* |
| auth deep link → register-with-auth | D-5 (updated) |

**Gap:** deep link `humanitec://pairing?code=` from settings UI (F-16).

### 2.6 Platform backend

| Surface | Test file | Gap |
|---|---|---|
| LLM proxy models/chat/stream/billing | LLM-01..03 | **LLM-04 stream SSE**, **LLM-05 billing span** |
| register / register-with-auth / discover | REG-AUTH-*, D-5 | — |
| tunnel WS multipod | tunnel_e2e, multipod | — |
| device policy shell/browser | ACC-07, F-11 | browser policy toggle UI |
| audit | ACC-04, PMCP-07 | — |

---

## 3. Принципы написания новых тестов

1. **Файл:** `tests/agent/desktop_e2e/test_agent_desktop_goose_*.py` или `tests/agent/e2e/`.
2. **Именование:** `{area}_{nn}_{verb}` — попадает в `check_agent_e2e_coverage.py`.
3. **Setup:** `humanitec_desktop_process_factory` → `desktop.start()` → CDP → **pair + LLM ready** (см. P0) → goosed session.
4. **Tool call:** только через `goosed_call_tool` / chat UI — не прямой import Rust.
5. **LLM в chat-тестах:** `mock_llm_with_queue` + `@pytest.mark.real_taskiq`.
6. **Assert:** содержимое tool response + side effect на disk/state, не snapshot строк.
7. **Регистрация:** добавить функцию в `REQUIRED_FUNCTIONS` + строку в `AGENT_E2E_COVERAGE_MATRIX.md` + suffix в `REQUIRED_TOOL_SUFFIXES` если новый tool.

---

## 4. План закрытия gaps (приоритеты)

### P0 — блокеры (сейчас ломает suite)

| ID | Задача | Действие |
|---|---|---|
| P0-01 | goosed `missing provider` | Shared helper `ensure_humanitec_paired_and_llm_ready(desktop, page, http_client, auth_token)`; вызывать из всех goose prepare_* и dev tests без pair |
| P0-02 | `test_e2e_download_asset_name_mismatch` | Изолировать local release: `AGENT__RELEASES__SOURCE=github` + missing repo **или** unset local artifact in test |
| P0-03 | `test_e2e_releases_status_github_404` | То же — local artifact делает `ready=true` |
| P0-04 | Пересборка DMG после branding | `apply_branding.sh` + `make agent-ensure` в CI/local перед desktop E2E |

### P1 — Goose tools: довести contract до 100% call-level

| ID | Test | Tool suffix |
|---|---|---|
| GOOSE-PLAT-04 | `test_goose_plat_04_extensionmanager_manage` | `manage_extensions` |
| GOOSE-PLAT-05 | `test_goose_plat_05_extensionmanager_resources` | `list_resources`, `read_resource` |
| GOOSE-PLAT-06 | `test_goose_plat_06_summon_delegate` | `delegate` |
| GOOSE-PLAT-07 | `test_goose_plat_07_apps_create_launch` | apps CRUD |
| GOOSE-PLAT-10 | `test_goose_plat_10_chatrecall_search` | chatrecall call |
| GOOSE-PLAT-12 | `test_goose_plat_12_summarize_call` | summarize call |
| GOOSE-CE-01 | `test_goose_ce_01_execute_typescript` | `execute_typescript` |
| GOOSE-CE-02 | `test_goose_ce_02_get_function_details` | `get_function_details` |
| GOOSE-DEV-08 | `test_goose_dev_08_text_editor` | `text_editor` (если есть в tools/list) |
| LLM-04 | `test_e2e_llm_proxy_chat_completions_stream` | SSE chunks |
| LLM-05 | `test_e2e_llm_proxy_billing_span` | platform_tracing span |

### P2 — Humanitec product flows

| ID | Сценарий |
|---|---|
| H-01 | Settings «Открыть в HumanitecAgent» deep link (Playwright) |
| H-02 | Settings «Войти через браузер» → auth → register-with-auth (E2E) |
| H-03 | LLM chat через Platform Brain: goosed chat → `/agent/llm/v1/chat/completions` (CDP + network log) |
| H-04 | Revoke во время LLM stream |
| H-05 | Second device + LLM autoconfig |
| H-06 | `humanitec://pairing` без code → pairing window (D-7 extended) |

### P3 — goosed/ACP surface (optional v1)

Recipes, schedules, dictation, local-inference, session export — только если продуктово включаем в HumanitecAgent.

---

## 5. CI gates (расширить)

| Gate | Сейчас | Добавить |
|---|---|---|
| `check_agent_e2e_coverage.py` | function names | новые P1 tests |
| `check_agent_goose_tool_contract.py` | suffixes static scan | platform + code_execution suffixes |
| `check_agent_test_no_monkeypatch.py` | e2e + desktop_e2e | keep |
| `make test` phase 4 | agent e2e + desktop | fix P0 first |
| Nightly | — | `make test-agent` full (~900s) |
| OS matrix | macos-arm64 local | CI: linux-deb optional job |

---

## 6. Makefile / pytest markers

```makefile
# Уже есть:
make test-agent              # full agent suite
make test-agent-e2e          # HTTP only, fast
make test-agent-desktop-e2e  # Electron + settings UI
make test-agent-goose-one TEST=...  # один тест, отладка
```

Рекомендация:
- `@pytest.mark.agent_desktop_e2e` — autouse skip если нет DMG (`ensure_humanitec_desktop_release_artifact`).
- `@pytest.mark.agent_goose_tool` — для фильтра `-m agent_goose_tool`.

---

## 7. Порядок реализации (спринты)

### Sprint A (1–2 дня): P0 — suite green
1. `ensure_humanitec_paired_and_llm_ready` в `helpers.py`
2. Подключить во все `prepare_goosed_*` и goose tests без pair
3. Починить 2 API e2e (local release isolation)
4. Прогон: `make test-agent-e2e` + `make test-agent-goose-extensions`

### Sprint B (3–5 дней): P1 platform + code_execution
1. Расширить `REQUIRED_TOOL_SUFFIXES`
2. 8 новых GOOSE-PLAT/CE tests
3. LLM stream + billing span

### Sprint C (2–3 дня): P2 Humanitec UX
1. F-16/F-17 UI E2E
2. H-03 Platform Brain chat E2E

### Sprint D: документация contract
1. Sync `openapi.json` goosed `/agent/call_tool`
2. Убрать phantom PLAT-04..12 из matrix или закрыть

---

## 8. Результаты прогона (2026-06-27)

```bash
make test-agent-e2e
# 76 passed, 2 failed (61s)
# FAIL: test_e2e_releases_status_github_404 — local DMG → ready=true
# FAIL: test_e2e_download_asset_name_mismatch — 307 redirect вместо 404

uv run pytest tests/agent/desktop_e2e/.../test_goose_dev_01_list_directory -n0
# FAIL: goosed HTTP 500: Could not configure agent: missing provider
# Причина: тест не делает pair + LLM autoconfig (HumanitecOnboardingGuard)

scripts/check_agent_e2e_coverage.py      # OK
scripts/check_agent_goose_tool_contract.py  # OK
scripts/check_agent_test_no_monkeypatch.py  # OK
```

---

## 9. Карта «не трогать — уже сделано»

Полный список реализованных test IDs — **`AGENT_E2E_COVERAGE_MATRIX.md`** (~120+ сценариев).  
Новая работа только по таблицам §4 (gaps) и P0 blockers.

---

## 10. Out of scope (явно)

- Flows-as-models в Goose provider list
- LitServe как LLM backend для agent proxy
- WS→HTTP fallback в desktop
- Мок goosed / mock Electron / stub tunnel
- Goose recipes/schedules/dictation без продуктового решения
