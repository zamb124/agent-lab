.PHONY: test test-all test-up test-down test-cov test-cov-all test-cov-report test-browser test-unit test-ui test-ui-components

WORKERS ?= 3
PYTEST_COMMAND_TIMEOUT_SECONDS ?= 600
PYTEST_MAX_WORKER_RESTART ?= 0
RUN_UI_IN_TEST ?= 0

# E2E UI (pytest + Playwright) и старый каталог browser — не гонять в unit/cov без инфраструктуры
_PYTEST_IGNORE_UI := --ignore=tests/frontend/browser --ignore=tests/ui

test-up:
	docker-compose -f docker-compose-test.yaml up -d postgres-test redis-test minio-test onlyoffice-documentserver test-a2a-agent flows_worker_test scheduler_test rag_worker_test livekit-test livekit-egress-test livekit-cli-test
	@echo "Ожидание готовности сервисов (postgres, redis, minio, onlyoffice, test-a2a-agent, worker, scheduler, livekit, livekit-egress, livekit-cli)..."
	@sleep 7

test-down:
	docker-compose -f docker-compose-test.yaml stop postgres-test redis-test minio-test onlyoffice-documentserver test-a2a-agent flows_worker_test scheduler_test rag_worker_test livekit-test livekit-egress-test livekit-cli-test

# Запуск unit/API тестов параллельно (без browser тестов)
test-unit: test-up
	@echo "Запуск unit/API тестов в $(WORKERS) воркерах..."
	uv run python -c "import subprocess,sys; r=subprocess.run(sys.argv[1:], timeout=$(PYTEST_COMMAND_TIMEOUT_SECONDS)); raise SystemExit(r.returncode)" uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration"

# Алиас: E2E UI (сценарии в tests/ui/e2e, фикстуры в tests/ui)
test-browser: test-up
	@echo "Запуск E2E UI (pytest tests/ui/e2e)..."
	uv run pytest tests/ui/e2e -v --timeout=180

# E2E UI: pytest + Playwright + фикстуры из tests/fixtures (нужны test-up)
test-ui: test-up
	@echo "Запуск E2E UI (pytest tests/ui/e2e)..."
	uv run pytest tests/ui/e2e -v --timeout=180

# Компонентные Lit-тесты (Web Test Runner, без реального бэкенда)
test-ui-components:
	@echo "Запуск компонентных UI-тестов (npm run test:ui-components)..."
	npm ci
	npm run test:ui-components

# Полный запуск: unit параллельно -> retry упавших -> browser
test: test-up
	@echo "=== 1/3 Запуск unit/API тестов в $(WORKERS) воркерах ==="
	@set +e; \
	phase1_rc=0; \
	phase2_rc=0; \
	phase3_rc=0; \
	uv run python -c "import subprocess,sys; r=subprocess.run(sys.argv[1:], timeout=$(PYTEST_COMMAND_TIMEOUT_SECONDS)); raise SystemExit(r.returncode)" uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration"; \
	phase1_rc=$$?; \
	echo ""; \
	echo "=== 2/3 Перезапуск упавших тестов (без параллелизации) ==="; \
	uv run python -c "import subprocess,sys; r=subprocess.run(sys.argv[1:], timeout=$(PYTEST_COMMAND_TIMEOUT_SECONDS)); raise SystemExit(r.returncode)" uv run pytest tests/ --lf \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration" -v; \
	phase2_rc=$$?; \
	if [ "$(RUN_UI_IN_TEST)" = "1" ]; then \
		echo ""; \
		echo "=== 3/3 Запуск E2E UI (pytest tests/ui/e2e) ==="; \
		uv run pytest tests/ui/e2e -v --timeout=180; \
		phase3_rc=$$?; \
	fi; \
	if [ $$phase1_rc -ne 0 ] || [ $$phase2_rc -ne 0 ] || [ $$phase3_rc -ne 0 ]; then \
		exit 1; \
	fi

test-all: test-up
	@echo "=== 1/3 Запуск всех unit/API тестов в $(WORKERS) воркерах ==="
	@set +e; \
	phase1_rc=0; \
	phase2_rc=0; \
	phase3_rc=0; \
	uv run python -c "import subprocess,sys; r=subprocess.run(sys.argv[1:], timeout=$(PYTEST_COMMAND_TIMEOUT_SECONDS)); raise SystemExit(r.returncode)" uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI); \
	phase1_rc=$$?; \
	echo ""; \
	echo "=== 2/3 Перезапуск упавших тестов (без параллелизации) ==="; \
	uv run python -c "import subprocess,sys; r=subprocess.run(sys.argv[1:], timeout=$(PYTEST_COMMAND_TIMEOUT_SECONDS)); raise SystemExit(r.returncode)" uv run pytest tests/ --lf \
		$(_PYTEST_IGNORE_UI) -v; \
	phase2_rc=$$?; \
	echo ""; \
	echo "=== 3/3 Запуск E2E UI (pytest tests/ui/e2e) ==="; \
	uv run pytest tests/ui/e2e -v --timeout=180; \
	phase3_rc=$$?; \
	if [ $$phase1_rc -ne 0 ] || [ $$phase2_rc -ne 0 ] || [ $$phase3_rc -ne 0 ]; then \
		exit 1; \
	fi

test-cov: test-up
	@echo "Запуск тестов с покрытием в $(WORKERS) воркерах (без browser)..."
	uv run python -c "import subprocess,sys; r=subprocess.run(sys.argv[1:], timeout=$(PYTEST_COMMAND_TIMEOUT_SECONDS)); raise SystemExit(r.returncode)" uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		-m "not integration" \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov

test-cov-all: test-up
	@echo "Запуск всех тестов с покрытием..."
	uv run python -c "import subprocess,sys; r=subprocess.run(sys.argv[1:], timeout=$(PYTEST_COMMAND_TIMEOUT_SECONDS)); raise SystemExit(r.returncode)" uv run pytest tests/ -n $(WORKERS) --max-worker-restart=$(PYTEST_MAX_WORKER_RESTART) \
		$(_PYTEST_IGNORE_UI) \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov
	uv run pytest tests/ui/e2e -v --timeout=180 \
		--cov=apps --cov=core --cov-append --cov-report=term-missing --cov-report=html:htmlcov

test-cov-report:
	@echo "Генерация HTML отчета покрытия..."
	uv run coverage html
	@echo "Отчет сохранен в htmlcov/index.html"
