.PHONY: test test-until-fail test-all test-static test-up test-down test-reset test-cov test-cov-all test-cov-report test-unit test-network test-ui test-ui-doc test-ui-components test-frontend-core test-frontend-core-canon test-frontend-core-unit test-frontend-core-browser test-profile check-strict-agent-architecture check-wider-repo-strictness agent-ensure test-agent test-agent-e2e test-agent-desktop-e2e

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

# Все тесты параллельны: xdist_group/сериализация запрещены (testing.mdc, «Parallel-safe контракты»).
_PYTEST_XDIST := -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART)

# Coverage (default-on): TEST_COVERAGE=0 make test
COV_RUN_ID := $(if $(filter 1,$(TEST_COVERAGE)),$(shell date +%Y%m%dT%H%M%S),)
ifeq ($(TEST_COVERAGE),1)
_COV_ARGS := --cov=apps --cov=core
_COV_ARGS_APPEND := --cov=apps --cov=core --cov-append
else
_COV_ARGS :=
_COV_ARGS_APPEND :=
endif

test-static:
	@$(MAKE) --no-print-directory _lint-py
	@uv run python scripts/check_agent_e2e_coverage.py
	@uv run python scripts/check_agent_goose_tool_contract.py
	@uv run python scripts/check_agent_test_no_monkeypatch.py

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
	docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) up -d --pull $(DOCKER_COMPOSE_PULL) postgres-test redis-test minio-test onlyoffice-documentserver provider_litserve test-a2a-agent livekit-test livekit-egress-test livekit-cli-test loki-test tempo-test alloy-test grafana-test
	@echo "Ожидание готовности сервисов (postgres, redis, minio, onlyoffice, provider_litserve, test-a2a-agent, livekit, livekit-egress, livekit-cli, loki, tempo, alloy, grafana)..."
	@sleep 7
	@echo "Сброс тестовой БД (TRUNCATE managed таблиц + Redis FLUSHDB)..."
	@uv run python -m scripts.db_test_reset
	@echo "Применение Alembic-миграций всех сервисных деревьев..."
	@uv run python -m scripts.test_migrate
	@echo "Старт стека сервисов (granian + TaskIQ) через test_stack..."
	@WORKERS=$(WORKERS) uv run python -m scripts.test_stack up

# Ручной сброс тестовой БД и Redis без поднятия контейнеров.
test-reset:
	@uv run python -m scripts.db_test_reset

test-down:
	@uv run python -m scripts.test_stack down
	docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) stop postgres-test redis-test minio-test onlyoffice-documentserver provider_litserve test-a2a-agent livekit-test livekit-egress-test livekit-cli-test loki-test tempo-test alloy-test grafana-test

# Запуск unit/API тестов параллельно (без browser тестов)
test-unit: test-up
	@echo "Запуск unit/API тестов в $(WORKERS) воркерах..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration and not network"

# Live-тесты с реальными HTTP-запросами в интернет (маркер network) — вне дефолтного прогона
test-network: test-up
	@echo "Запуск network-тестов (реальные HTTP-запросы в интернет)..."
	uv run pytest tests/ -m "network" $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		$(_PYTEST_IGNORE_AGENT_DESKTOP)

# E2E UI: pytest + Playwright + фикстуры из tests/fixtures (нужны test-up)
test-ui: test-up
	@echo "Запуск E2E UI (pytest tests/ui/e2e)..."
	UI_E2E_USE_LVH_ME=1 uv run pytest tests/ui/e2e -v --timeout=180

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
		uv run pytest tests/ui/e2e -v --timeout=180 $(_COV_ARGS_APPEND); \
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
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent/desktop_e2e tests/ui/e2e/test_frontend_settings_agent.py -n0 --timeout=900 $(_COV_ARGS_APPEND); \
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
	uv run pytest tests/ui/e2e -v --timeout=180; \
	phase3_rc=$$?; \
	if [ $$phase1_rc -ne 0 ] || [ $$phase2_rc -ne 0 ] || [ $$phase3_rc -ne 0 ]; then \
		exit 1; \
	fi

test-cov: test-up
	@echo "Запуск тестов с покрытием в $(WORKERS) воркерах (без browser)..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration and not network" \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov

test-cov-all: test-up
	@echo "Запуск всех тестов с покрытием..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ $(_PYTEST_XDIST) \
		$(_PYTEST_IGNORE_UI) \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov
	uv run pytest tests/ui/e2e -v --timeout=180 \
		--cov=apps --cov=core --cov-append --cov-report=term-missing --cov-report=html:htmlcov

test-cov-report:
	@echo "Генерация HTML отчета покрытия..."
	uv run coverage html
	@echo "Отчет сохранен в htmlcov/index.html"

test-agent: test-up
	uv run python scripts/check_agent_e2e_coverage.py
	uv run python scripts/check_agent_goose_tool_contract.py
	uv run python scripts/check_agent_test_no_monkeypatch.py
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent tests/frontend/api/test_humanitec_agent_api.py tests/flows/api/test_agent_platform_mcp.py tests/ui/e2e/test_frontend_settings_agent.py -v -n0 --timeout=900

test-agent-e2e: test-up
	uv run pytest tests/agent/e2e -v -n0 --timeout=180

test-agent-desktop-e2e: test-up
	uv run python scripts/check_agent_e2e_coverage.py
	uv run python scripts/check_agent_goose_tool_contract.py
	AGENT_ARTIFACT_MODE=release uv run python scripts/agent_build.py ensure-local --artifact-mode release --version-sha "$$(git rev-parse HEAD)"
	RUN_UI_IN_TEST=1 UI_E2E_USE_LVH_ME=1 uv run pytest tests/agent/desktop_e2e tests/ui/e2e/test_frontend_settings_agent.py -v -n0 --timeout=900

test-agent-ui-e2e: test-up
	UI_E2E_USE_LVH_ME=1 RUN_UI_IN_TEST=1 uv run pytest tests/ui/e2e/test_frontend_settings_agent.py -n0 --timeout=300
