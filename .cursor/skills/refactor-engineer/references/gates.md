# Гейты

Норма → гейт закреплены в разделе «Гейты» правила-владельца; здесь — как гейты запускать и читать. Все шаги `make lint` в режиме отчёта — `.cursor/skills/refactor-engineer/scripts/gates_report.py`.

## Состав `make lint`

- `make lint` = `_lint-py` + `lint-ts` (`mk/lint.mk`), `set -e`: остановка на первом упавшем шаге. `make lint <path>` — ruff + basedpyright на файл (`.py`) или `lint-ts` (`.js`).
- `lint-ts` = `check-events-canon` (`Makefile`) + `scripts/check_ui_kit_docs.py` + `check-field-canon` + `check-logging`.
- `make test-static` (`mk/test.mk`) = `_lint-py` + `scripts/pin_a2a_official_fixtures.py --check` + agent-гейты + `tests/core/ai/test_platform_model_scoring_fixtures.py`.
- Вне `make lint`: `make check-a2a-fixtures`, `make check-ft-wheels` (`scripts/check_ft_wheels.sh`), `make check-gpu-dockerfile-llm-model`, проверки документации (`scripts/check_docs_locale_parity.py`, `scripts/check_scenario_docs_quality.py`); отчёты без fail — `scripts/report_ui_i18n_gaps.py`, `scripts/report_ui_cyrillic.sh`.

## `_lint-py`

| Гейт | Держит | Allowlist |
|---|---|---|
| `ruff check apps core` | E, F, I, W (`pyproject.toml`, без E501) | exclude `apps/agent/desktop/vendor` |
| `scripts/check_strict_agent_architecture.py` | отсутствие удалённых символов flows/agent, UI-контракты reflection, code_agent, observability | контракты в скрипте |
| `scripts/audit_wider_repo_strictness.py` | `getattr(..., default)` без классификации | `GETATTR_DECISIONS` |
| `scripts/check_files_canon.py`, `scripts/check_files_ui_canon.sh` | байты только через Files API, chunked upload, Documents bind | `ALLOWLIST_PATHS` |
| `scripts/check_tool_tags.py` | один tag из whitelist на builtin tool | `TOOL_TAG_WHITELIST` |
| `scripts/check_tool_contracts.py` | `parameters_schema` с `additionalProperties=false`, запрет `ServiceClient`/`CallParameter` в tools | `SERVICE_CLIENT_ALLOWLIST` |
| `scripts/check_office_file_id_canon.py` | публичный id документа — `file_id` | исключения путей vendor/desktop |
| `scripts/check_cross_service_imports.py` | нет импортов `apps/<a>` → `apps/<b>` | правила в docstring скрипта |
| `scripts/check_command_owner_catalogs.py` | владелец в `_OWNER_BY_SCOPE` ⇔ непустой `<SVC>_OPERATIONS`, ключи `*_requested` | — |
| `scripts/check_rest_handlers_call_ops.py` | REST-хендлер сервиса из `COMMAND_WS_SERVICES` зовёт `op_*` | `PROTOCOL_HANDLERS` (протоколы, принцип) |
| `scripts/check_billing_span_canon.py` | `record_usage` только в settlement; `pending_settlement` покрыт правилом | `REQUIRE_BALANCE_*`, `RECORD_LLM_*` (принцип) |
| `scripts/check_conf_secrets.py` | секреты `conf.json` — плейсхолдеры `YOUR_*` | `ALLOWED_PATHS` |
| `scripts/check_conf_keys_declared.py` | каждый ключ `conf.json` объявлен в Settings | — |
| `scripts/check_repo_hygiene.py` | корень репозитория по allowlist | allowlist корня (принцип) |
| `scripts/check_ratchet_counts.py` | 14 счётчиков долга не растут (`scripts/ratchet_baseline.json`) | baseline = весь долг |
| `scripts/check_dependency_injection_canon.py` | контракт `di.py`, DI только на boundary, параметр `di` | boundary-префиксы (принцип) |
| `scripts/check_backend_error_i18n.py` | `platform:errors` ru ≡ en, `error_code` у `WsCommandError`, кириллица в `raise` | `scripts/backend_error_i18n_baseline.json` |
| `scripts/check_mcp_branding_bundle.py` | бандл брендинга MCP | — |
| `scripts/check_platform_brand_hardcode.py` | нет хардкода apex-домена | `ALLOWLIST_PATHS` |
| `scripts/check_authz_canon.py` | sole PDP, нет roster-Check, мутации членства в тестах через `sync_company_member_roles` | `FGA_ONLY_*` (принцип) |
| `scripts/check_authz_dual_write.py` | create/delete ACL-ресурса пишет tuple в том же call path | маркеры в скрипте |
| `scripts/check_authz_backfill_completeness.py` | tuple-helper покрыт backfill | — |
| `scripts/check_authz_model.py` | тесты модели OpenFGA | — |
| `basedpyright --level warning --warnings apps core` | типы, warning = fail | exclude в `pyproject.toml` |
| `analyze_imports.py` | локальные импорты: цель `Total local imports: 0` | — |
| `scripts/check_agent_e2e_coverage.py`, `scripts/check_agent_goose_tool_contract.py`, `scripts/check_agent_test_no_monkeypatch.py` | E2E LinnexAgent, контракт goose-тулов, без моков в agent e2e | — |
| `scripts/check_variables_legacy.sh` | нет старого API переменных | — |
| `scripts/check_redis_ttl_canon.py` | TTL у каждого ключа Redis, `from_url` только в разрешённых точках | `REDIS_FROM_URL_*` |
| `scripts/check_taskiq_canon.py` | только `declare_task` + `@platform_task` + `enqueue` | `KIQ_*`, `CREATE_BROKER_*` (инфраструктурные точки) |

## `check-events-canon`

| Цель | Гейт | Держит |
|---|---|---|
| `check-core-frontend-canon` | `scripts/check_core_frontend_canon.py`, `scripts/check_embed_esm_closure.py` | канон `core/frontend/static/lib/**`, ESM-замыкание embed |
| `check-ui-canon` | `scripts/check_ui_canon.sh` (пункты 0–37), `scripts/check_flow_ui_hard_cut.py`, `scripts/check_platform_typography.py` | UI-канон сервисов, грамматика Flow UI, шрифты |
| `check-ui-factories` | `scripts/check_ui_factories.py` | форма фабрик, `transport`, `restMirror` |
| `check-command-rest-mirror` | `scripts/check_command_rest_mirror.py` | `restMirror` ↔ FastAPI route, `transport: 'ws'`; allowlist `COMMAND_WS_HTTP_ALLOWLIST` |
| `check-platform-events-canon` | `scripts/check_platform_events_canon.py` | шина и каталог событий |
| `check-realtime-canon` | `scripts/check_realtime_canon.py` | Centrifugo HTTP только у bus `realtime` |
| `check-voice-*` | `scripts/check_voice_resolver_usage.py`, `scripts/check_speakable_parity.py`, `scripts/check_tts_pipeline_single_apply.py` | голос через `voice_resolver`, pronunciation pipeline |
| `check-rag-post-retrieval-rerank` | `scripts/check_rag_post_retrieval_rerank_single.py` | один реранк |
| `check-file-reader-canon`, `check-corpus-manifest` | `scripts/check_file_reader_canon.py`, `scripts/check_corpus_manifest_complete.py` | чтение файлов только `FileReader.read`, полный корпус |
| `check-company-ai` | `scripts/check_company_ai_canon.py` | модели только через `core.ai` |
| `check-files-canon`, `check-mcp-branding-bundle` | см. `_lint-py` | — |
| `check-i18n`, `check-i18n-keys` | `scripts/check_i18n.sh`, `scripts/check_i18n_keys.py --mode missing --strict` | пары ru/en, ключи ↔ код |
| `check-no-uvicorn` | `scripts/check_no_uvicorn.sh` | Granian only |

`check-field-canon` — `scripts/check_field_canon.sh` (сырые `<input>`/`<textarea>`/`<select>`); `check-logging` — `scripts/check_logging_canon.sh` + `scripts/_check_print_calls.py`.

## Чтение вывода

- Скрипты собирают все нарушения и выходят с 1; `make lint` прячет следующие шаги за первым падением — поэтому отчёт идёт через `gates_report.py`.
- Мягкие режимы: `scripts/check_i18n_keys.py` без `--strict`, `scripts/check_command_rest_mirror.py` и `scripts/check_ui_factories.py` без `--strict` печатают предупреждения без fail.
- Ratchet: рост — FAIL; снижение — OK и подсказка `--update`. Файлы по метрике — `.cursor/skills/refactor-engineer/scripts/ratchet_list.py <metric>`. Текущее число ниже baseline — лимит не подтянут: `uv run python scripts/check_ratchet_counts.py --update`.
- `analyze_imports.py`: читать `Total local imports`, а не код выхода.

## Allowlist: принцип или долг

- Принцип (не сокращается срезом): `PROTOCOL_HANDLERS`, `COMMAND_WS_HTTP_ALLOWLIST`, инфраструктурные точки Redis/TaskIQ, billing entrypoints, allowlist корня репозитория, `FGA_ONLY_*`. Каждый пункт — `Исключение:` в правиле-владельце.
- Долг (сокращается срезами до 0): ratchet-baseline, `scripts/backend_error_i18n_baseline.json`, пути в `ALLOWLIST_PATHS`, не оформленные `Исключение:` в правиле.
- Новый пункт allowlist ради зелёного прогона запрещён; принципиальный — только вместе с `Исключение:` в правиле-владельце.
