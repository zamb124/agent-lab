.PHONY: test test-all test-static test-up test-down test-reset test-cov test-cov-all test-cov-report test-unit test-ui test-ui-doc test-ui-components test-frontend-core test-frontend-core-canon test-frontend-core-unit test-frontend-core-browser test-profile check-strict-agent-architecture check-wider-repo-strictness

WORKERS ?= 5
PYTEST_COMMAND_TIMEOUT_SECONDS ?= 5400
PYTEST_MAX_WORKER_RESTART ?= 2
RUN_UI_IN_TEST ?= 0
DOCKER_COMPOSE_PULL ?= missing
DOCKER_COMPOSE_ENV_FILE ?= .env.test-compose-images
PYTHON_CHECK_PATHS ?= apps core
RUFF_CHECK_ARGS ?= $(PYTHON_CHECK_PATHS)
BASEDPYRIGHT_CHECK_ARGS ?= --level warning --warnings $(PYTHON_CHECK_PATHS)

# E2E UI (pytest + Playwright) — не гонять в unit/cov без инфраструктуры
_PYTEST_IGNORE_UI := --ignore=tests/ui

test-static:
	@$(MAKE) --no-print-directory _lint-py

check-strict-agent-architecture:
	@uv run python scripts/check_strict_agent_architecture.py

check-wider-repo-strictness:
	@uv run python scripts/audit_wider_repo_strictness.py

test-up: runtime-bootstrap
	@uv run python scripts/ensure_test_compose_images.py
	docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) up -d --pull $(DOCKER_COMPOSE_PULL) postgres-test redis-test minio-test onlyoffice-documentserver provider_litserve test-a2a-agent livekit-test livekit-egress-test livekit-cli-test loki-test tempo-test alloy-test grafana-test
	@echo "Ожидание готовности сервисов (postgres, redis, minio, onlyoffice, provider_litserve, test-a2a-agent, livekit, livekit-egress, livekit-cli, loki, tempo, alloy, grafana)..."
	@sleep 7
	@echo "Сброс тестовой БД (TRUNCATE managed таблиц + Redis FLUSHDB)..."
	@uv run python -m scripts.db_test_reset

# Ручной сброс тестовой БД и Redis без поднятия контейнеров.
test-reset:
	@uv run python -m scripts.db_test_reset

test-down:
	docker-compose -f docker-compose-test.yaml --env-file $(DOCKER_COMPOSE_ENV_FILE) stop postgres-test redis-test minio-test onlyoffice-documentserver provider_litserve test-a2a-agent livekit-test livekit-egress-test livekit-cli-test loki-test tempo-test alloy-test grafana-test

# Запуск unit/API тестов параллельно (без browser тестов)
test-unit: test-up
	@echo "Запуск unit/API тестов в $(WORKERS) воркерах..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration"

# E2E UI: pytest + Playwright + фикстуры из tests/fixtures (нужны test-up)
test-ui: test-up
	@echo "Запуск E2E UI (pytest tests/ui/e2e)..."
	uv run pytest tests/ui/e2e -v --timeout=180

# E2E UI + статическая документация (README в docs/scenarios из scenario_doc)
test-ui-doc: test-ui
	@echo "Сборка documentation-dist после UI-тестов..."
	@$(MAKE) doc

# Opt-in: asyncio loop slow callbacks + FileLock waits (см. scripts/run_pytest_profile.py).
test-profile: test-up
	@echo "Runtime profile: FileLock + event loop (отчёт /tmp/platform_test_runtime_profile_merged.json)..."
	uv run python scripts/run_pytest_profile.py tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration" -q

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
	@npm run test:core-unit

test-frontend-core-browser: runtime-bootstrap
	@echo "Layer 3/3: браузерные тесты (Web Test Runner + Playwright)..."
	@npm ci --silent
	@npm run test:core-browser

test-frontend-core: test-frontend-core-canon test-frontend-core-unit test-frontend-core-browser
	@echo "core/frontend: 3/3 OK"

# Полный запуск: Python static -> фундамент UI -> unit параллельно -> retry упавших -> browser
test:
	@$(MAKE) --no-print-directory test-static
	@$(MAKE) --no-print-directory test-frontend-core
	@$(MAKE) --no-print-directory test-up
	@echo "=== 1/3 Запуск unit/API тестов в $(WORKERS) воркерах ==="
	@set +e; \
	phase1_rc=0; \
	phase2_rc=0; \
	phase3_rc=0; \
	rm -f .pytest_cache/v/cache/lastfailed; \
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration"; \
	phase1_rc=$$?; \
	if [ $$phase1_rc -ne 0 ]; then \
		echo ""; \
		echo "=== 2/3 Перезапуск упавших тестов (без параллелизации) ==="; \
			uv run python scripts/run_pytest_lastfailed.py --timeout $(PYTEST_COMMAND_TIMEOUT_SECONDS) -- -n 1 --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
				$(_PYTEST_IGNORE_UI) \
				-m "not integration" -v; \
		phase2_rc=$$?; \
		if [ $$phase2_rc -eq 0 ]; then \
			phase1_rc=0; \
		fi; \
	else \
		echo ""; \
		echo "=== 2/3 Перезапуск упавших тестов пропущен: первая фаза зелёная ==="; \
	fi; \
	if [ "$(RUN_UI_IN_TEST)" = "1" ]; then \
		echo ""; \
		echo "=== 3/3 Запуск E2E UI (pytest tests/ui/e2e) ==="; \
		uv run pytest tests/ui/e2e -v --timeout=180; \
		phase3_rc=$$?; \
	fi; \
	if [ $$phase1_rc -ne 0 ] || [ $$phase2_rc -ne 0 ] || [ $$phase3_rc -ne 0 ]; then \
		exit 1; \
	fi

test-all:
	@$(MAKE) --no-print-directory test-static
	@$(MAKE) --no-print-directory test-frontend-core
	@$(MAKE) --no-print-directory test-up
	@echo "=== 1/3 Запуск всех unit/API тестов в $(WORKERS) воркерах ==="
	@set +e; \
	phase1_rc=0; \
	phase2_rc=0; \
	phase3_rc=0; \
	rm -f .pytest_cache/v/cache/lastfailed; \
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI); \
	phase1_rc=$$?; \
	if [ $$phase1_rc -ne 0 ]; then \
		echo ""; \
		echo "=== 2/3 Перезапуск упавших тестов (без параллелизации) ==="; \
			uv run python scripts/run_pytest_lastfailed.py --timeout $(PYTEST_COMMAND_TIMEOUT_SECONDS) -- -n 1 --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
				$(_PYTEST_IGNORE_UI) -v; \
		phase2_rc=$$?; \
		if [ $$phase2_rc -eq 0 ]; then \
			phase1_rc=0; \
		fi; \
	else \
		echo ""; \
		echo "=== 2/3 Перезапуск упавших тестов пропущен: первая фаза зелёная ==="; \
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
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration" \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov

test-cov-all: test-up
	@echo "Запуск всех тестов с покрытием..."
	uv run python scripts/pytest_with_timeout.py $(PYTEST_COMMAND_TIMEOUT_SECONDS) uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov
	uv run pytest tests/ui/e2e -v --timeout=180 \
		--cov=apps --cov=core --cov-append --cov-report=term-missing --cov-report=html:htmlcov

test-cov-report:
	@echo "Генерация HTML отчета покрытия..."
	uv run coverage html
	@echo "Отчет сохранен в htmlcov/index.html"
