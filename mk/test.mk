.PHONY: test test-until-fail test-all test-static test-up test-down test-reset test-cov test-cov-all test-cov-report test-unit test-network test-ui test-ui-chat test-ui-doc test-ui-components test-ui-kit test-ui-kit-playwright test-ui-kit-doc ui ui-doc test-frontend-core test-frontend-core-canon test-frontend-core-unit test-frontend-core-browser test-profile check-strict-agent-architecture check-wider-repo-strictness agent-ensure test-observability

WORKERS ?= 10
DB_PROFILE ?= 1
PYTEST_WORKERS_PROFILE ?= 1
TEST_COVERAGE ?= 1
PYTEST_COMMAND_TIMEOUT_SECONDS ?= 5400
PYTEST_MAX_WORKER_RESTART ?= 2
RUN_UI_IN_TEST ?= 0
DOCKER_COMPOSE_PULL ?= missing
DOCKER_COMPOSE_ENV_FILE ?= .env.test-compose-images
PYTHON_CHECK_PATHS ?= apps core
RUFF_CHECK_ARGS ?= $(PYTHON_CHECK_PATHS)
BASEDPYRIGHT_CHECK_ARGS ?= --level warning --warnings $(PYTHON_CHECK_PATHS)

# E2E UI (pytest + Playwright) — browser; agent desktop E2E только в phase 4 (-n0, Electron)
_PYTEST_IGNORE_UI := --ignore=tests/ui
_PYTEST_IGNORE_AGENT_DESKTOP := --ignore=tests/agent/desktop_e2e
_PYTEST_IGNORE_AGENT_E2E := --ignore=tests/agent/e2e

# Все тесты параллельны: xdist_group/сериализация запрещены (testing.mdc § Параллельный прогон).
_PYTEST_XDIST := -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART)

# Coverage (default-on): TEST_COVERAGE=0 make test
COV_RUN_ID := $(if $(filter 1,$(TEST_COVERAGE)),$(shell date +%Y%m%dT%H%M%S),)
ifeq ($(TEST_COVERAGE),1)
# --cov-report= глушит дефолтный term-dump pytest-cov (все файлы).
# Итоговый terminal report (top-20 worst files) печатает scripts/test_coverage_report.py.
_COV_ARGS := --cov=apps --cov=core --cov-report=
_COV_ARGS_APPEND := --cov=apps --cov=core --cov-append --cov-report=
else
_COV_ARGS :=
_COV_ARGS_APPEND :=
endif

test-static:
	@$(MAKE) --no-print-directory _lint-py
	@uv run python scripts/pin_a2a_official_fixtures.py --check
	@uv run python scripts/check_agent_e2e_coverage.py
	@uv run python scripts/check_agent_goose_tool_contract.py
	@uv run python scripts/check_agent_test_no_monkeypatch.py
	@uv run pytest -q tests/core/ai/test_platform_model_scoring_fixtures.py

check-strict-agent-architecture:
	@uv run python scripts/check_strict_agent_architecture.py

check-wider-repo-strictness:
	@uv run python scripts/audit_wider_repo_strictness.py

test-up: runtime-bootstrap
	@echo "Preflight: остановка предыдущего test_stack (granian + TaskIQ)..."
	@uv run python -m scripts.test_stack down 2>/dev/null || true
	@echo "Preflight: зачистка stale pytest/granian/taskiq/code-runner процессов..."
	@uv run python -m scripts.test_process_preflight_cleanup
	@uv run python scripts/ensure_test_compose_images.py
	docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) up -d --pull $(DOCKER_COMPOSE_PULL) postgres-test redis-test redis-realtime-test centrifugo-test seaweedfs-test seaweedfs-test-ext onlyoffice-documentserver provider_litserve test-a2a-agent livekit-test livekit-egress-test livekit-cli-test loki-test tempo-test alloy-test grafana-test
	@echo "Ожидание готовности сервисов (postgres, redis, redis-realtime, centrifugo, seaweedfs, seaweedfs-ext, onlyoffice, provider_litserve, test-a2a-agent, livekit, livekit-egress, livekit-cli, loki, tempo, alloy, grafana)..."
	@sleep 7
	@echo "Сброс тестовой БД (TRUNCATE managed таблиц + Redis FLUSHDB)..."
	@uv run python -m scripts.db_test_reset
	@echo "Накат 0001_initial всех сервисных баз (+ CREATE DATABASE openfga)..."
	@uv run python -m scripts.test_migrate
	@echo "Старт OpenFGA (после создания БД openfga)..."
	@docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) rm -f -s openfga-migrate-test openfga-test >/dev/null 2>&1 || true
	@docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) up -d --force-recreate --pull $(DOCKER_COMPOSE_PULL) openfga-migrate-test openfga-test
	@echo "Bootstrap OpenFGA store + authorization model..."
	@uv run python scripts/openfga_env_bootstrap.py --api-url http://127.0.0.1:9093 --env-path reports/openfga-test.env
	@echo "Старт стека сервисов (granian + TaskIQ) через test_stack..."
	@WORKERS=$(WORKERS) uv run python -m scripts.test_stack up

# Ручной сброс тестовой БД и Redis без поднятия контейнеров.
test-reset:
	@uv run python -m scripts.db_test_reset

test-down:
	@uv run python -m scripts.test_stack down
	docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) stop postgres-test redis-test redis-realtime-test centrifugo-test seaweedfs-test seaweedfs-test-ext onlyoffice-documentserver provider_litserve test-a2a-agent livekit-test livekit-egress-test livekit-cli-test loki-test tempo-test alloy-test grafana-test openfga-test

# Запуск unit/API тестов параллельно (без browser тестов)
test-unit: test-up
	@echo "Запуск unit/API тестов в $(WORKERS) воркерах..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration and not network"

test-observability: test-up
	@echo "Запуск observability product-metric тестов..."
	uv run pytest tests/unit/test_observability_dashboards.py \
		tests/core/tracing/test_operation_log_mirror.py \
		tests/observability/ -q --tb=short
	uv run pytest tests/observability/ -m real_taskiq -q --tb=short

# Live-тесты с реальными HTTP-запросами в интернет (маркер network) — вне дефолтного прогона
test-network: test-up
	@echo "Запуск network-тестов (реальные HTTP-запросы в интернет)..."
	uv run pytest tests/ -m "network" $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		$(_PYTEST_IGNORE_AGENT_DESKTOP)

# E2E UI: pytest + Playwright + фикстуры из tests/fixtures (нужны test-up)
# UI E2E: xdist workers, изоляция company+MockLLM scope (tests/ui/e2e_worker.py).
UI_E2E_WORKERS ?= 5

test-ui: test-up
	@echo "Обеспечение HumanitecAgent release artifacts..."
	@AGENT_ARTIFACT_MODE=release $(MAKE) --no-print-directory agent-ensure
	@echo "Запуск E2E UI (pytest tests/ui/e2e, -n$(UI_E2E_WORKERS) --dist=loadfile, default 15s/test)..."
	@rm -rf artifacts/ui-perf
	UI_E2E_USE_LVH_ME=1 uv run pytest tests/ui/e2e -n$(UI_E2E_WORKERS) --dist=loadfile -v --timeout=15
	@echo "UI perf SUMMARY: artifacts/ui-perf/SUMMARY.md"

# Быстрый прогон chat-related UI E2E (flows chat-page, embed autoload, landing drawer)
test-ui-chat: test-up
	@echo "Запуск chat UI E2E (pytest tests/ui/e2e/test_flows_chat_page.py tests/ui/e2e/test_embed_autoload_browser.py tests/ui/e2e/test_landing_demo_chat_drawer.py)..."
	@rm -rf artifacts/ui-perf
	UI_E2E_USE_LVH_ME=1 uv run pytest tests/ui/e2e/test_flows_chat_page.py tests/ui/e2e/test_embed_autoload_browser.py tests/ui/e2e/test_landing_demo_chat_drawer.py -n$(UI_E2E_WORKERS) --dist=loadfile -v --timeout=15
	@echo "UI perf SUMMARY: artifacts/ui-perf/SUMMARY.md"

# E2E UI + статическая документация (README в docs/scenarios из scenario_doc)
test-ui-doc: test-ui
	@echo "Сборка documentation-dist после UI-тестов..."
	@$(MAKE) doc

# Opt-in: asyncio loop slow callbacks + FileLock waits (см. scripts/run_pytest_profile.py).
test-profile: test-up
	@echo "Runtime profile: FileLock + event loop (отчёт /tmp/platform_test_runtime_profile_merged.json)..."
	uv run python scripts/run_pytest_profile.py tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration and not network" -q

# Компонентные Lit-тесты (Web Test Runner, без реального бэкенда)
test-ui-components: runtime-bootstrap
	@echo "Запуск компонентных UI-тестов (npm run test:ui-components)..."
	npm ci
	npm run test:ui-components

# ==============================================================================
# Frontend core: трёхслойная проверка фундамента event-архитектуры.
#   Layer 1 — статический канон (regex по core/frontend/static/lib/**) — секунды.
#   Layer 2 — pure-node unit (Vitest + MSW + MockWebSocket) — секунды.
#   Layer 3 — браузерные тесты (Web Test Runner + Playwright Chromium) — десятки секунд.
# Каждый следующий слой стартует только если предыдущий зелёный.
# Полный test-frontend-core — обязательная зависимость make test (fail-fast).
# ==============================================================================

test-frontend-core-canon:
	@echo "Layer 1/3: канон core/frontend (regex)..."
	@uv run python scripts/check_core_frontend_canon.py

test-frontend-core-unit: runtime-bootstrap
	@echo "Layer 2/3: pure-node unit (Vitest)..."
	@npm ci --silent
	@if [ "$(TEST_COVERAGE)" = "1" ]; then \
		test -n "$(COV_RUN_ID)"; \
		mkdir -p reports/coverage/$(COV_RUN_ID)/js; \
		npx vitest run --config vitest.config.mjs --coverage \
			--coverage.reportsDirectory=reports/coverage/$(COV_RUN_ID)/js \
			--coverage.reporter=text --coverage.reporter=lcov --coverage.reporter=html; \
	else \
		npm run test:core-unit:fast; \
	fi

test-frontend-core-browser: runtime-bootstrap
	@echo "Layer 3/3: браузерные тесты (Web Test Runner + Playwright)..."
	@npm ci --silent
	@npm run test:core-browser

# Сборка UI-бандлов: esbuild per-app → apps/<svc>/ui-dist/ (index.js + hashed chunks + ассеты).
ui-build: runtime-bootstrap
	@echo "ui-build: esbuild bundles → ui-dist/"
	@npm ci --silent
	@npm run build:ui

# Typecheck всех .ts (strict). Конверсия идёт инкрементально — см. ratchet ui_js_files.
ui-typecheck: runtime-bootstrap
	@echo "ui-typecheck: tsc --noEmit"
	@npm ci --silent
	@npx tsc -p tsconfig.json

# Dev watch: пересборка бандлов на изменение (параллельно с make app).
ui-watch: runtime-bootstrap
	@npm ci --silent
	@npm run watch:ui

# Единая локальная проверка UI: сборка + typecheck + канон + core frontend (canon/unit/browser incl. UI Kit L1).
ui: ui-build ui-typecheck lint-ts test-frontend-core
	@echo "ui: OK"

# UI + Playwright L2 doc scenarios (нужен test-up) + regenerate docs/scenarios/platform/ui-kit/**
ui-doc: ui test-ui-kit-doc
	@echo "ui-doc: OK"

test-ui-kit: runtime-bootstrap
	@echo "UI Kit L1: design-system contract specs (Web Test Runner)..."
	@npm ci --silent
	@npm run test:ui-kit

test-ui-kit-playwright: test-up
	@echo "UI Kit L2: Playwright component doc scenarios..."
	@uv run pytest tests/ui/design-system/components/**/playwright.spec.py -v -m ui_component

test-ui-kit-doc: test-ui-kit-playwright
	@echo "UI Kit: regenerate docs/scenarios/platform/ui-kit/**"
	@uv run python scripts/generate_ui_kit_docs.py

test-frontend-core: test-frontend-core-canon test-frontend-core-unit test-frontend-core-browser
	@echo "core/frontend: 3/3 OK"

# Полный запуск: Python static -> фундамент UI -> unit параллельно -> retry упавших -> browser
test:
	@$(MAKE) --no-print-directory test-static
	@$(MAKE) --no-print-directory runtime-bootstrap
	@AGENT_ARTIFACT_MODE=release $(MAKE) --no-print-directory agent-ensure
	@$(MAKE) --no-print-directory test-frontend-core TEST_COVERAGE=$(TEST_COVERAGE) COV_RUN_ID=$(COV_RUN_ID)
	@$(MAKE) --no-print-directory test-up
	@if [ "$(DB_PROFILE)" = "1" ]; then \
		echo "=== DB profile: reset pg_stat_statements ==="; \
		uv run python -m scripts.db_test_profile reset; \
	fi
	@echo "=== 1/4 Запуск unit/API тестов в $(WORKERS) воркерах ==="
	@set +e; \
	export LOGGING__LEVEL=WARNING; \
	PROFILE_RUN_ID=""; \
	if [ "$(DB_PROFILE)" = "1" ] || [ "$(PYTEST_WORKERS_PROFILE)" = "1" ]; then \
		PROFILE_RUN_ID=$$(date +%Y%m%dT%H%M%S); \
		mkdir -p reports/pytest_workers_profile/$$PROFILE_RUN_ID; \
	fi; \
	if [ "$(TEST_COVERAGE)" = "1" ]; then \
		echo "=== Test coverage: reset (run $(COV_RUN_ID)) ==="; \
		uv run python -m scripts.test_coverage_report reset --run-id $(COV_RUN_ID) --workers $(WORKERS); \
		export COVERAGE_FILE=reports/coverage/$(COV_RUN_ID)/.coverage; \
	fi; \
	phase1_rc=0; \
	phase2_rc=0; \
	phase3_rc=0; \
	phase4a_rc=0; \
	phase4c_rc=0; \
	rm -f .pytest_cache/v/cache/lastfailed; \
	JUNIT_XML_ARG=""; \
	if [ "$(PYTEST_WORKERS_PROFILE)" = "1" ]; then \
		JUNIT_XML_ARG="--junitxml=reports/pytest_workers_profile/$$PROFILE_RUN_ID/junit.xml"; \
	fi; \
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$$JUNIT_XML_ARG \
		$(_PYTEST_IGNORE_UI) \
		$(_PYTEST_IGNORE_AGENT_DESKTOP) \
		$(_PYTEST_IGNORE_AGENT_E2E) \
		$(_COV_ARGS) \
		-m "not integration and not network and not agent_build_release"; \
	phase1_rc=$$?; \
	if [ "$(DB_PROFILE)" = "1" ]; then \
		echo ""; \
		echo "=== DB profile: collect + report (phase 1) ==="; \
		uv run python -m scripts.db_test_profile collect --run-id $$PROFILE_RUN_ID; \
		uv run python -m scripts.db_test_profile report --run-id $$PROFILE_RUN_ID; \
		echo "DB profile: terminal summary above; HTML reports/db_test_profile/latest/report.html"; \
	fi; \
	if [ "$(PYTEST_WORKERS_PROFILE)" = "1" ]; then \
		echo ""; \
		echo "=== Pytest workers profile: collect + report (phase 1) ==="; \
		uv run python -m scripts.pytest_workers_profile collect --run-id $$PROFILE_RUN_ID \
			--workers $(WORKERS) --exit-code $$phase1_rc; \
		uv run python -m scripts.pytest_workers_profile report --run-id $$PROFILE_RUN_ID; \
		echo "Pytest workers profile: terminal summary above; HTML reports/pytest_workers_profile/latest/report.html"; \
	fi; \
	if [ $$phase1_rc -ne 0 ]; then \
		echo ""; \
		echo "=== 2/4 Перезапуск упавших тестов (без параллелизации) ==="; \
			uv run python scripts/run_pytest_lastfailed.py --timeout $(PYTEST_COMMAND_TIMEOUT_SECONDS) -- -n 1 --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
				$(_PYTEST_IGNORE_UI) \
				$(_PYTEST_IGNORE_AGENT_DESKTOP) \
				$(_PYTEST_IGNORE_AGENT_E2E) \
				$(_COV_ARGS_APPEND) \
				-m "not integration and not network and not agent_build_release" -v; \
		phase2_rc=$$?; \
		if [ $$phase2_rc -eq 0 ]; then \
			phase1_rc=0; \
		fi; \
	else \
		echo ""; \
		echo "=== 2/4 Перезапуск упавших тестов пропущен: первая фаза зелёная ==="; \
	fi; \
	if [ "$(RUN_UI_IN_TEST)" = "1" ]; then \
		echo ""; \
		echo "=== 3/4 Запуск E2E UI (pytest tests/ui/e2e) ==="; \
		uv run pytest tests/ui/e2e -v --timeout=15 $(_COV_ARGS_APPEND); \
		phase3_rc=$$?; \
	fi; \
	echo ""; \
	echo "=== 4/4 HumanitecAgent (gates + release artifact + HTTP E2E + desktop E2E + settings UI) ==="; \
	uv run python scripts/check_agent_e2e_coverage.py; \
	uv run python scripts/check_agent_goose_tool_contract.py; \
	uv run python scripts/check_agent_test_no_monkeypatch.py; \
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"; \
	rm -f /tmp/platform_test_pytest_controller.pid; \
	uv run pytest tests/agent/e2e tests/flows/api/test_agent_platform_mcp.py tests/frontend/api/test_humanitec_agent_api.py -n0 --timeout=180 $(_COV_ARGS_APPEND); \
	phase4a_rc=$$?; \
	rm -f /tmp/platform_test_pytest_controller.pid; \
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 AGENT_DESKTOP_E2E_RUN=1 uv run pytest tests/agent/desktop_e2e tests/ui/e2e/test_frontend_settings_agent.py -n0 --timeout=15 $(_COV_ARGS_APPEND); \
	phase4c_rc=$$?; \
	if [ "$(TEST_COVERAGE)" = "1" ]; then \
		echo ""; \
		echo "=== Test coverage: report (run $(COV_RUN_ID)) ==="; \
		uv run python -m scripts.test_coverage_report report --run-id $(COV_RUN_ID); \
	fi; \
	if [ $$phase1_rc -ne 0 ] || [ $$phase2_rc -ne 0 ] || [ $$phase3_rc -ne 0 ] || [ $$phase4a_rc -ne 0 ] || [ $$phase4c_rc -ne 0 ]; then \
		exit 1; \
	fi

# Как make test до phase 1 pytest, но -x: останов на первом FAILED/ERROR без retry и phase 4.
test-until-fail:
	@$(MAKE) --no-print-directory test-static
	@$(MAKE) --no-print-directory runtime-bootstrap
	@AGENT_ARTIFACT_MODE=release $(MAKE) --no-print-directory agent-ensure
	@$(MAKE) --no-print-directory test-frontend-core
	@$(MAKE) --no-print-directory test-up
	@echo "=== pytest phase 1 (exit on first failure, -x) ==="
	@rm -f /tmp/platform_test_pytest_controller.pid .pytest_cache/v/cache/lastfailed
	@export LOGGING__LEVEL=WARNING; \
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		-x -v --tb=short \
		$(_PYTEST_IGNORE_UI) \
		$(_PYTEST_IGNORE_AGENT_DESKTOP) \
		$(_PYTEST_IGNORE_AGENT_E2E) \
		-m "not integration and not network"

test-all:
	@$(MAKE) --no-print-directory test-static
	@$(MAKE) --no-print-directory agent-ensure
	@$(MAKE) --no-print-directory test-frontend-core
	@$(MAKE) --no-print-directory test-up
	@echo "=== 1/4 Запуск всех unit/API тестов в $(WORKERS) воркерах ==="
	@set +e; \
	export LOGGING__LEVEL=WARNING; \
	phase1_rc=0; \
	phase2_rc=0; \
	phase3_rc=0; \
	rm -f .pytest_cache/v/cache/lastfailed; \
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI); \
	phase1_rc=$$?; \
	if [ $$phase1_rc -ne 0 ]; then \
		echo ""; \
		echo "=== 2/4 Перезапуск упавших тестов (без параллелизации) ==="; \
			uv run python scripts/run_pytest_lastfailed.py --timeout $(PYTEST_COMMAND_TIMEOUT_SECONDS) -- -n 1 --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
				$(_PYTEST_IGNORE_UI) -v; \
		phase2_rc=$$?; \
		if [ $$phase2_rc -eq 0 ]; then \
			phase1_rc=0; \
		fi; \
	else \
		echo ""; \
		echo "=== 2/4 Перезапуск упавших тестов пропущен: первая фаза зелёная ==="; \
	fi; \
	echo ""; \
	echo "=== 3/3 Запуск E2E UI (pytest tests/ui/e2e) ==="; \
	uv run pytest tests/ui/e2e -v --timeout=15; \
	phase3_rc=$$?; \
	if [ $$phase1_rc -ne 0 ] || [ $$phase2_rc -ne 0 ] || [ $$phase3_rc -ne 0 ]; then \
		exit 1; \
	fi

test-cov: test-up
	@echo "Запуск тестов с покрытием в $(WORKERS) воркерах (без browser)..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration and not network" \
		--cov=apps --cov=core --cov-report= --cov-report=html:htmlcov
	@uv run python -m scripts.test_coverage_report term

test-cov-all: test-up
	@echo "Запуск всех тестов с покрытием..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		--cov=apps --cov=core --cov-report= --cov-report=html:htmlcov
	uv run pytest tests/ui/e2e -v --timeout=15 \
		--cov=apps --cov=core --cov-append --cov-report= --cov-report=html:htmlcov
	@uv run python -m scripts.test_coverage_report term

test-cov-report:
	@echo "Генерация HTML отчета покрытия..."
	uv run coverage html
	@uv run python -m scripts.test_coverage_report term
	@echo "Отчет сохранен в htmlcov/index.html"

# LLM context layer: unit + adapter + flows wiring + e2e (MockLLM only)
test-llm-context: test-up
	@echo "Запуск LLM context layer coverage suite..."
	uv run pytest \
		tests/core/llm_context \
		tests/core/clients/llm/test_context_layer.py \
		tests/core/rag/test_llm_context_memory_store.py \
		tests/core/rag/test_llm_context_source.py \
		tests/flows/core/resources/test_llm_context_memory.py \
		tests/flows/core/resources/test_llm_context_rag.py \
		tests/flows/core/resources/test_llm_context_resource.py \
		tests/flows/core/resources/test_llm_context_runtime.py \
		tests/flows/core/llm_nodes/test_llm_context_config.py \
		tests/flows/core/llm_nodes/test_llm_context_wiring.py \
		tests/flows/e2e/llm_context \
		-q --tb=short
