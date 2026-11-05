# Тесты: стек, прогоны, триаж

Процедура. Нормы (моки, изоляция, фикстуры, таймауты, стиль теста) — `testing.mdc`; lint до тестов — `main.mdc` § Lint gate. Здесь — как поднять стек, выбрать прогон и разобрать падение.

## Какой прогон

| Изменение | Прогон |
|---|---|
| Узкая правка домена | `make test-up` один раз, затем `uv run pytest tests/<домен>/ -q` |
| DI, транспорт команд, контракт, runtime, тестовая инфраструктура | архитектурные тесты (§ Архитектурные тесты), затем `make test` |
| Нужен coverage или менялись тестовые гейты | `make test-cov` |
| UI | § Слои UI-тестов |

Целевой прогон домена:

```bash
make test-up                                   # один раз на сессию работы
uv run pytest tests/<домен>/ -q                # домен
uv run pytest tests/<домен>/ -q -n 5           # домен под xdist
uv run pytest tests/<path>.py::test_name -q    # один тест
uv run pytest tests/ -n 5 -m "not integration and not network"
```

## Тестовый стек

`make test-up` (`mk/test.mk`) — единственный путь поднять стек. Шаги по порядку:

1. `runtime-bootstrap` — `scripts/dev/bootstrap_runtimes.py`.
2. `uv run python -m scripts.testing.stack down` — остановка прошлого стека.
3. `uv run python -m scripts.testing.process_preflight_cleanup` (`scripts/testing/process_preflight_cleanup.py`) — зачистка stale pytest, granian, TaskIQ и code-runner процессов по точным сигнатурам и портам.
4. `uv run python -m scripts.testing.ensure_compose_images` — GHCR auth (`gh auth login` + `docker login`), pull-or-build образов, файл `.env.test-compose-images`. Транспортную ошибку `docker manifest inspect` (IPv6 `socket is not connected`) скрипт ретраит; `unauthorized` — повторный login; `manifest unknown` — raise; сетевая ошибка не выдаётся за «нет образа».
5. `docker-compose -f docker-compose-test.yaml up -d` — Postgres `:54322`, Redis `:63792`, redis-realtime `:63793`, Centrifugo `:19000`, SeaweedFS `:19002`, OnlyOffice `:18088`, provider_litserve, `test-a2a-agent` `:18052`, LiveKit, Loki, Tempo, Alloy, Grafana.
6. `uv run python -m scripts.testing.db_reset` (`scripts/testing/db_reset.py`) — TRUNCATE managed-таблиц всех баз и Redis FLUSHDB. Backend Postgres завис в `BgworkerShutdown` и `pg_terminate_backend` не снимает lock'и — скрипт делает один `docker restart agentlab_postgres_test` и повторяет drain.
7. `uv run python -m scripts.testing.migrate` (`scripts/testing/migrate.py`) — цепочка миграций всех сервисных баз и сид компании `system`.
8. OpenFGA — `openfga-migrate-test` и `openfga-test` (`:9093`), `scripts/dev/openfga_env_bootstrap.py` пишет store и модель в `reports/openfga-test.env`.
9. `WORKERS=$(WORKERS) uv run python -m scripts.testing.stack up` (`scripts/testing/stack.py`) — параллельный старт granian-сервисов (9001–9026) и TaskIQ-воркеров, параллельное ожидание readiness, манифест `/tmp/platform_test_stack.json` (`pytest_workers_requested`, `stack_scale_factor`, `stack_capacity`).

```bash
make test-down                                   # test_stack down + compose stop
make test-reset                                  # только TRUNCATE + FLUSHDB, без контейнеров
uv run python -m scripts.testing.stack status       # состояние процессов по манифесту
tail -f /tmp/platform_test_stack/<name>.err      # логи процесса стека (<name>.log / <name>.err)
```

Readiness стека — 180 с (`STACK_READINESS_TIMEOUT_SEC`), `provider_litserve` — 240 с: десятки granian и TaskIQ-процессов импортируются одновременно около двух минут, 90–120 с ложно роняют поздние `worktracker`, `capability_gateway`, `idle_worker`. Readiness-фикстуры pytest ретраят 30 с: стек уже поднят, но под stampede старта xdist health отвечает не сразу.

Смена кода воркера или reader'а — перезапуск стека (`make test-up`): процессы стека не перечитывают код.

Postgres теста: `max_connections=800`, `shm_size: 1g`, данные в named volume `postgres-test-data`. Смена `max_connections` или `auto_explain` — `docker-compose -f docker-compose-test.yaml up -d --force-recreate postgres-test` (PGDATA сохраняется); полный wipe данных — только явный `down -v`. Дефолтный `/dev/shm` Docker (64M) под `-n10` даёт `DiskFullError`.

## Профили `make test`

`make test` по шагам: `test-static` → `runtime-bootstrap` → `test-frontend-core` (канон → Vitest → WTR) → `test-up` → этап 1: `pytest tests/ -n $(WORKERS)` без `tests/ui` и маркеров `integration`, `network` под `scripts/testing/pytest_with_timeout.py` → этап 2: догон не сыгранных тестов `-n $(WORKERS)` (`scripts/testing/pytest_notrun.py` — покрывает обрыв сессии INTERNALERROR/краш воркера, которых `lastfailed` не видит) → повтор упавших `-n 1` (`scripts/testing/pytest_lastfailed.py`) → этап 3: `tests/ui/e2e` только при `RUN_UI_IN_TEST=1`.

| Переменная | Дефолт | Смысл |
|---|---|---|
| `WORKERS` | `10` | pytest-воркеры этапа 1; `auto` = 10; стек масштабируется от baseline 10 |
| `DB_PROFILE` | `1` | `pg_stat_statements` reset после `test-up`, collect и отчёт после этапа 1: `reports/db_test_profile/latest/report.html`; пороги `DB_PROFILE_SLOW_MS`, `DB_PROFILE_SLOW_TOTAL_MS`, `DB_PROFILE_TOP_N`, `DB_PROFILE_TERMINAL_TOP_N`; `NO_COLOR=1` |
| `PYTEST_WORKERS_PROFILE` | `1` | отчёт параллелизма после этапа 1 (`reports/pytest_workers_profile/latest/report.html`); issues `stack_undersized`, `phase1_failed`, `likely_parallelism_failure`, `xdist_bottleneck`, `worker_restart_risk` |
| `TEST_COVERAGE` | `1` | Python `apps`+`core` этапов 1, 2, 4 и Vitest → `reports/coverage/latest/report.html`; печатается и при exit 1. ~30% CPU надбавка на процесс — при диагностике таймаутов/параллелизма гоняйте `TEST_COVERAGE=0` |
| `PYTEST_COMMAND_TIMEOUT_SECONDS` | `5400` | wall-clock `scripts/testing/pytest_with_timeout.py` (убивает process group) |
| `PYTEST_MAX_WORKER_RESTART` | `2` | `--max-worker-restart` xdist |
| `RUN_UI_IN_TEST` | `0` | этап 3 UI E2E |

Остальные цели `mk/test.mk`:

```bash
make test WORKERS=15          # больше воркеров + масштабированный стек
make test-until-fail          # как make test до этапа 1, но -x: стоп на первом FAILED/ERROR
make test-unit                # xdist без tests/ui и маркеров integration, network; без профилей
make test-all                 # все маркеры без tests/ui, повтор упавших, затем UI E2E
make test-network             # только @pytest.mark.network (реальный интернет)
make test-observability       # product-metric тесты observability
make test-llm-context         # набор LLM context layer
make test-profile             # asyncio slow callbacks + FileLock waits (/tmp/platform_test_runtime_profile_merged.json)
make test-cov / make test-cov-all / make test-cov-report
DB_PROFILE=0 PYTEST_WORKERS_PROFILE=0 TEST_COVERAGE=0 make test   # без профилей
```

## Ёмкость стека (baseline `WORKERS=10`)

Источник чисел — `scripts/testing/stack.py`. `WORKERS > 10` масштабирует отмеченные сервисы до `ceil(baseline × WORKERS / 10)`; меньше 10 — baseline.

| Процесс | workers | Почему столько |
|---|---|---|
| `flows` granian | 14 | CRM note-analyze A2A на live `:9001` делит процесс с параллельными A2A e2e |
| `crm` granian | 8 | 10 gw бьют `/crm/api`; 1 worker — HOL `GET /tasks` и knowledge-import |
| `secrets` granian | 4 | A2A analyze делает `require_can_view(company)` на resolve |
| `capability_gateway` granian | 6 | capability-вызовы sandbox из всех gw |
| `code_runner_python`, `_node`, `_go`, `_csharp` | 12 (+ `CODE_RUNNER_*_WORKERS=12`) | один granian на go/csharp: неограниченные `dotnet`/`go build` под `-n10` дают ReadTimeout 60 с |
| `search` granian, `search_worker`, `sync_worker` | 2 | — |
| `crm_summary_worker` | 2 | daily/period summary идут очередью `crm_summary`, а не `crm` |
| `flows_worker` | 8 | OCC ledger — per `session_id`; один consumer сериализует A2A, note-analyze остаётся `running` до poll 90 с |
| `crm_worker` | 16 | import `notes_only` не ждёт в HOL за analyze, который ждёт A2A на flows |
| `idle_worker` | 2 | не масштабируется |
| `rag_worker`, `a2a_push_worker`, остальные granian | 1 | не масштабируются |

Недостаточная ёмкость при полном прогоне проявляется как `ServiceClientError`/`ReadTimeout` к `code_runner_python`, `NodeWallClockTimeoutError` в public search и `TaskiqResultTimeoutError` на параллельных tool/flow тестах. Executor'ы code-runner python/node раздают запросы через очередь свободных worker'ов (`_acquire_worker`/`_release_worker`), поэтому длинный запрос не блокирует соседей.

## Таймауты пакетов

Лимиты ставит `pytest_collection_modifyitems` в `tests/conftest.py` (для пакета без своего маркера); UI E2E — `tests/ui/e2e/conftest.py`, realtime — `tests/realtime/conftest.py`.

| Пакет | Лимит | `func_only` |
|---|---|---|
| `@pytest.mark.real_taskiq` | 180 с | `False`: setup `crm_client`/`rag_worker` под `-n10` и shared Postgres дольше 5 с |
| `tests/crm/e2e/**` | 120 с | `False`; перекрывает более короткий маркер и `func_only=True`, явный ≥120 с с `func_only=False` не трогает |
| sandbox: `tests/capabilities/**`, `tests/flows/integration/**`, `tests/flows/e2e/**`, `_CODE_RUNNER_TEST_PREFIXES` | 180 с | `True` |
| RAG global maintenance (`tests/core/rag/test_execute_reembed_tick_integration.py`, `delete_orphan_company_chunks` в `tests/rag/test_pgvector_provider.py`) | 120 с | `False` |
| `tests/core/websocket/test_notification_e2e.py` | 120 с | `False` |
| `tests/sync/db/**`, `tests/files/**`, `file_retention_purge` в `tests/idle/test_idle_worker_tasks.py` | 60 с | `True` |
| `tests/flows/api/test_a2a.py`, `tests/flows/api/test_flows_variables.py`, `tests/flows/api/test_sessions_api.py`, `tests/flows/core/db/test_session_repository_search.py`, `tests/frontend/api/test_public_search_session.py` | 60 с | `True` |
| `tests/flows/api/test_flow_ui_shares.py`, `tests/flows/api/test_reload_flow_from_bundle.py`, `tests/flows/api/test_company_init_commands.py`, `tests/core/clients/test_sync_client.py` | 60 с | `True`; in-process A2A flow exec / bundle reload / реальный HTTP под xdist — без бюджета pytest-timeout флагает на 5 с, hang_guard убивает воркер на +15 с (каскад рестартов) |
| `tests/core/integrations/test_google_workspace_emulator_auth.py`, `tests/frontend/test_team_act_as.py` | 30 с | `True` |
| `tests/realtime/**` | 20 с | — |
| `tests/ui/e2e/**` | 15 с, до 360 с по `scenario(timeout_seconds=N)` или маркеру | `True` |

Почему CRM e2e — 120 с с `func_only=False`: setup `crm_client` и note-analyze через `crm_worker` под `-n10` не укладываются в 60 с; module `pytestmark = timeout(20)` давал FAILED на call и ERROR на setup. Это потолок зависания, а не бюджет тела: poll `_analyze_note` — 90 с (`tests/crm/e2e/test_05_ai_analysis.py`), бюджет A2A GetTask — `analysis_a2a_timeout_seconds` (90 с, `apps/crm/config.py`). Долгий note-analyze лечится причиной:

- очередь `flows_worker` (ёмкость, § Ёмкость стека);
- лишний `GET /.well-known/agent-card.json`: `A2AClient.send_task` AgentCard не запрашивает (→ `a2a.mdc`);
- `GET /flows/` не делает Check всего каталога: окна `page_viewable_flow_ids` и BatchCheck OpenFGA порциями; полный Check каталога под `-n10` занимает store, note-analyze висит до poll;
- `MockLLM` не режет stream на 2–5 символов: каждый чанк — durable emit, мелкие чанки держат CRM analyze `llm_node` около 80 с;
- CRM lifespan N granian: `crm_company_init_lock` (`pg_advisory_lock` на отдельном соединении) и UniqueViolation `company_mapping` как успех; `CompanyInitService.initialize_company` в pytest — insert-only (`reseed=False`);
- knowledge-import e2e не применяет seed `sales`: минимальный шаблон + `note`/`meeting`/`task`.

Почему sandbox — 180 с с `func_only=True`: пакеты autouse-зависят от HTTP `sandbox_services` (capability_gateway + code-runner на 9016–9020); глобальные 5 с дают ложный timeout, а не сигнал зависания runner. Изоляция code-node CRM — около 33 с; httpx2 `timeout` на `POST /flows/api/v1/code/execute` и `POST /flows/api/v1/code/lsp/session` — тоже 180 с (60 с на живом `:9001` под `-n10` даёт ReadTimeout в очереди granian).

Прочие ожидания: HTTP-фикстуры `*_client_http` — timeout 60 с (очередь granian, не бюджет графа); A2A HTTP e2e длинного графа — `returnImmediately` + GetTask poll 60 с (`a2a_wait_task_completed`, `tests/flows/_a2a_v1.py`), blocking `SendMessage` держит flows granian и под `-n10` даёт `httpx2.ReadTimeout`; пока задача в `TASK_STATE_SUBMITTED`/`TASK_STATE_WORKING`, poll пропускает ответ с `result: null`; `wait_result` TaskIQ — `TASKIQ_WAIT_RESULT_TIMEOUT_SECONDS` (90 с, `tests/fixtures/taskiq_timeouts.py`); tracing `_wait_spans` для graph-path ждёт `required_operation_substrings` до 30 с, а не первый span.

## Триаж падения

1. Первый fail — `/tmp/pytest-first-fail.txt` (xdist `-x` печатает traceback только после drain); зависший воркер — `/tmp/pytest-hung-worker.txt` (hang-guard SIGKILL gw, чей heartbeat setup/call/teardown старше timeout + 15 с; setup/teardown — не меньше 60 с; `idle` не трогается); xdist поднимает убитый gw до `--max-worker-restart`. Журнал убийств прогона — `/tmp/platform_test_hang_guard_kills.jsonl`, lifecycle сессий — `/tmp/platform_test_hang_guard_events.jsonl` (старт/финиш gw с pid; heartbeat прошлых прогонов чистится на старте мастера и heartbeat до старта монитора не убивается — защита от pid-reuse).
2. Логи процессов стека — `/tmp/platform_test_stack/<name>.err`; readiness и ёмкость — `uv run python -m scripts.testing.stack status`, `/tmp/platform_test_stack.json`.
3. Отчёты этапа 1 — `reports/pytest_workers_profile/latest/report.html` (`stack_undersized`, `likely_parallelism_failure`, `xdist_bottleneck`, `hang_guard_kills`, `worker_restarts`, `low_worker_utilization`, `phase1_truncated`; метрики `worker_utilization` = сумма времени junit / (workers × wall), wall из events.jsonl, `tests: executed/collected` — conftest пишет все собранные nodeids в `/tmp/platform_test_collected_nodeids.json`) и `reports/db_test_profile/latest/report.html` (медленные запросы).
4. Повтор изолированно: `uv run pytest <nodeid> -q -n 0`. Зелёный изолированно и красный под `-n10` — shared state или ёмкость: уникальные id и scope, single-owner глобального ключа, сходимость batch-операции, ёмкость стека. Красный изолированно — контракт или инфраструктура теста.
5. `ReadTimeout`, `TaskiqResultTimeoutError`, задача `running` до конца poll — очередь воркера, HOL granian, лишний запрос или Check OpenFGA (§ Таймауты пакетов), а не лимит.
6. 403 на secrets, files, RAG или namespace — нет tuples OpenFGA у субъекта: членство через `set_test_company_member_roles`, namespace через `NamespaceService`, пользователь `ExecutionState.user_id` — JWT-пользователь `auth_headers_system` (синтетический `user-{context_id}` без tuples получает deny).
7. `RuntimeError: tool authz gate is not bound` в unit-тесте тула — фикстура `bind_flow_tool_authz_context` (`tests/flows/_tool_authz_context.py`); in-process interrupt e2e — `user_id="test-user"` + `sync_company_member_roles` и явный `llm.provider=mock`.
8. `A2A Task identity belongs to another scope` — захардкоженный `task_id` без `unique_id` встретил leftover projection в общей БД.
9. `assert 0 >= 1` / `queue exhausted` в CRM — фоновый side-effect снял FIFO теста: у side-effect свой scope `{parent}:{kind}`.
10. После починки — `make test-until-fail` или целевой набор под `-n $(WORKERS)`.

## Рецепты

- **Полный E2E flows** (webhook → `process_flow_task` → LLM → channel HTTP): без `real_taskiq`; `sync_tools` исполняет `enqueue(TASK_PROCESS_FLOW, ...)` in-process, ответы — `mock_llm_redis`.
- **Воркер с MockLLM** (`@pytest.mark.real_taskiq` + `mock_llm_redis`): воркер читает FIFO после `init_worker_testing_mock_llm` (`core/tasks/worker_bootstrap.py`) на старте; пример — `tests/rag/test_index_file_extract_e2e.py` (+ `rag_worker`).
- **Эмбеддинги RAG без внешнего API**: `PgVectorProvider` (`core/rag/providers/pgvector_provider.py`) создаёт детерминированный embedding-клиент при `is_testing()` или `rag.embedding.mock` (ENV `RAG__EMBEDDING__MOCK`); процессы стека получают `TESTING=true` из `scripts/testing/stack.py`.
- **Исполняемый `llm_node` с MockLLM** — эталон `tests/flows/core/tools/test_google_docs_emulator_llm.py`.
- **Handoff** — матрица и порядок очереди MockLLM → `handoff.mdc`; Flow UI conformance → `flow_ui.mdc`; A2A conformance (`tests/flows/a2a_conformance/`) → `a2a.mdc`.
- **Квота по client IP**: фикстура с `ASGITransport(app=..., client=(ip, port))` и IP из `unique_id` (`tests/frontend/api/test_public_search_session.py`).
- **Office**: Document Server в Docker (`:18088`) обращается к office granian по `OFFICE__CALLBACK_PUBLIC_BASE_URL=http://host.docker.internal:9008`.
- **CRM E2E** читает `DATABASE__CRM_URL` из `tests/fixtures/test_database_env.py` (`:54322`, база `platform_crm`); новая миграция — `uv run python -m scripts.db.migrate upgrade --service crm` или `make test-up`.
- **Google Workspace live** (`-m network`: `tests/core/clients/test_google_sheets_client_live.py`, `tests/flows/core/tools/test_google_sheets_integration.py`, `tests/flows/core/tools/test_google_docs_integration.py`): OAuth-токен в `GOOGLE_ACCESS_TOKEN` или `google_workspace.live_test.access_token` (`conf.local.json`; scopes documents, spreadsheets, drive.file), либо service account + `GOOGLE_IMPERSONATE_EMAIL` с Domain-wide delegation (не `@gmail.com`). Запуск — `GOOGLE_ACCESS_TOKEN=... make test-network`.
- **Корпус FileReader** (`tests/core/files/example-docs/`, manifest `tests/core/files/corpus/overrides.yaml` + `tests/core/files/corpus/manifest_generated.py`): `make sync-example-docs`, `uv run python -m scripts.generate.corpus_manifest`, проверка — `make check-corpus-manifest`; файлы больше 5 MB — Git LFS; сверка с GitHub tree — `make test-network`.
- **Фикстуры LLM scoring** (`tests/core/ai/fixtures/scoring/`): обновление с реальными ключами — `uv run python -m scripts.generate.llm_scoring_fixtures`, drift — `--check`; live-smoke — `tests/core/ai/test_platform_model_scoring_live.py` (`make test-network`).
- **Сетевые тесты** (`integration`, `network`, пример `tests/core/files/test_file_writer_network.py`): вне дефолтного прогона — `pytest -m "not integration and not network"`, отдельно — `make test-network`.
- **Browser runtime** (`tests/browser/`): интеграция — `@pytest.mark.integration` с `BROWSER__CDP_URL`; E2E против Lightpanda — `BROWSER__E2E_LIGHTPANDA=1` и `BROWSER__E2E_LIGHTPANDA_CDP_URL` (или `BROWSER__CDP_URL`).
- **Property-based**: `uv run pytest -q tests/core/variables/test_template_scan_fuzz.py tests/core/code_contract/test_scanner_fuzz.py tests/flows/unit/test_flow_dataflow_inspector_fuzz.py`; frontend `*.fuzz.spec.ts` входит в `make test-frontend-core-unit`; воспроизводимая регрессия — `@seed(...)` Hypothesis.
- **`PytestCollectionWarning`** на доменном классе `Test*` (`cannot collect test class ... because it has a __init__`): `__test__ = False`, в Pydantic — `__test__: ClassVar[bool] = False`.
- **localhost на macOS**: granian стека слушает IPv4, `localhost` может резолвиться в `::1` — readiness и наборы URL используют `127.0.0.1`.

## Слои UI-тестов

```bash
make test-frontend-core          # канон core/frontend (regex) → Vitest → WTR; входит в make test
make test-frontend-core-canon    # scripts/gates/frontend/core_frontend_canon.py
make test-frontend-core-unit     # Vitest tests/frontend_core/unit (с coverage при TEST_COVERAGE=1)
make test-frontend-core-browser  # WTR: tests/frontend_core/browser + UI Kit contract + design-system flows
make test-ui-components          # npm ci + тот же WTR-конфиг
make test-ui-kit                 # UI Kit L1: только contract.spec.js
make test-ui-kit-playwright      # UI Kit L2: playwright.spec.py -m ui_component (нужен test-up)
make test-ui-kit-doc             # L2 + генерация docs/scenarios/platform/ui-kit/**
make ui                          # lint-ts + test-frontend-core
make ui-doc                      # ui + test-ui-kit-doc
make test-ui                     # test-up + tests/ui/e2e -n$(UI_E2E_WORKERS) --dist=loadfile
make test-ui-chat                # chat-срез UI E2E
make test-ui-doc                 # test-ui + make doc
UI_E2E_WORKERS=1 make test-ui    # serial для отладки
uv run playwright install chromium
```

- После правок `apps/*/ui/index.html`, import map, базовых классов (`PlatformElement`, `PlatformModal`, `*App`) или массовой замены импортов — `make test-frontend-core-browser`; затронуты shell или маршруты SPA — `uv run pytest tests/ui/`. Быстрый статический контроль — `make check-ui-canon`.
- Каждый прогон `tests/ui/e2e` пишет perf-отчёт (`tests/ui/perf/`): `artifacts/ui-perf/<worker>/<nodeid>.json` и `artifacts/ui-perf/SUMMARY.md` (медленные тесты, API paths, long tasks, 4xx/5xx); `make test-ui` и `make test-ui-chat` чистят каталог перед прогоном. Порогов нет — отчёт для поиска hotspots.
- Скриншоты шагов подсвечивают цель клика (`install_click_highlight_on_context`, `tests/ui/click_highlight.py`).
- `README.en.md` сценария без E2E-прогона — `uv run python -m scripts.docs.regenerate_scenario_readme_en`; отключить генерацию документации — `UI_SCENARIO_DOCS=0`; авторский стандарт инструкции — скил `documentator`, UI Kit docs → `ui_components.mdc`. Гайд — `tests/ui/README.md`.
- Сборка документации — `make doc`; опубликованный URL сценария — `/documentation/scenarios/<service>/<slug>/` (теги схлопываются, группировка — на hub-странице сервиса).

## Архитектурные тесты

После изменения DI, транспорта команд или контрактов:

```bash
uv run pytest -q tests/core/di/test_service_kit.py tests/core/di/test_service_kit_boundary.py \
  tests/core/realtime/test_command_owners.py tests/realtime/ \
  tests/flows/core/test_strict_agent_architecture.py tests/core/test_wider_repo_strictness_audit.py \
  tests/core/tasks/test_taskiq_canon.py
```

| Тест | Что держит |
|---|---|
| `tests/core/di/test_service_kit.py` | autowiring по типам конструкторов, recipes, lifecycle, ошибки графа |
| `tests/core/di/test_service_kit_boundary.py` | один alias `Di` на boundary FastAPI, TaskIQ и WS-каталога команд |
| `tests/core/realtime/test_command_owners.py` | каталог владельцев `*_requested` и регистрация команд в шине |
| `tests/realtime/test_<svc>_commands.py` | тождество WS ≡ REST каждой команды сервиса (live Centrifugo `:19000` + bus `:9025`) |
| `tests/flows/core/test_strict_agent_architecture.py` | `scripts/gates/backend/strict_agent_architecture.py` без нарушений |
| `tests/core/test_wider_repo_strictness_audit.py` | аудит `scripts/gates/backend/wider_repo_strictness.py` |
| `tests/core/tasks/test_taskiq_canon.py` | registry задач, labels `enqueue`, wiring брокеров |

## Дерево `tests/`

```text
tests/
├── conftest.py            # env теста, pytest_plugins, хуки таймаутов, autouse-фикстуры, MockLLM
├── hang_guard.py          # hang-guard xdist
├── fixtures/              # общие фикстуры: services, workers, clients, auth, service_processes, platform_events, эмуляторы
├── core/                  # core/* по доменам (di, realtime, authz, files, rag, ai, ...)
├── flows/                 # unit, api, core, integration, e2e, a2a_conformance, channels, tools, evals
├── crm/ sync/ rag/ office/ wiki/ worktracker/ stock/ search/ secrets/ scheduler/ voice/ browser/ guest_runtime/
├── realtime/              # live WS ≡ REST каждой команды
├── capabilities/          # sandbox-контур capability_gateway + code-runner
├── frontend/ files/ idle/ observability/ provider_litserve/ e2e/ unit/ utils/ scripts/
├── frontend_core/         # unit (Vitest), browser (WTR), helpers
└── ui/                    # движок UI-тестов; e2e/, design-system/, perf/
```
