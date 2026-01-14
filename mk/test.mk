.PHONY: test test-all test-up test-down test-cov test-cov-all test-cov-report test-browser test-unit

WORKERS ?= 2

test-up:
	docker-compose -f docker-compose-test.yaml up -d postgres-test chroma-test redis-test minio-test test-a2a-agent worker-test scheduler-test chroma-worker-test
	@echo "Ожидание готовности сервисов (postgres, chroma, redis, minio, test-a2a-agent, worker, scheduler)..."
	@sleep 7

test-down:
	docker-compose -f docker-compose-test.yaml stop postgres-test chroma-test redis-test minio-test test-a2a-agent worker-test scheduler-test chroma-worker-test

# Запуск unit/API тестов параллельно (без browser тестов)
test-unit: test-up
	@echo "Запуск unit/API тестов в $(WORKERS) воркерах..."
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser \
		-m "not integration"

# Запуск browser тестов последовательно (нужны серверы)
test-browser: test-up
	@echo "Запуск browser тестов (последовательно)..."
	uv run pytest tests/frontend/browser -v --timeout=180

# Полный запуск: unit параллельно -> retry упавших -> browser
test: test-up
	@echo "=== 1/3 Запуск unit/API тестов в $(WORKERS) воркерах ==="
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser \
		-m "not integration" || true
	@echo ""
	@echo "=== 2/3 Перезапуск упавших тестов (без параллелизации) ==="
	uv run pytest tests/ --lf \
		--ignore=tests/frontend/browser \
		-m "not integration" -v || true
	@echo ""
	@echo "=== 3/3 Запуск browser тестов (последовательно) ==="
	uv run pytest tests/frontend/browser -v --timeout=180 || true

test-all: test-up
	@echo "=== 1/3 Запуск всех unit/API тестов в $(WORKERS) воркерах ==="
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser || true
	@echo ""
	@echo "=== 2/3 Перезапуск упавших тестов (без параллелизации) ==="
	uv run pytest tests/ --lf \
		--ignore=tests/frontend/browser -v || true
	@echo ""
	@echo "=== 3/3 Запуск browser тестов (последовательно) ==="
	uv run pytest tests/frontend/browser -v --timeout=180 || true

test-cov: test-up
	@echo "Запуск тестов с покрытием в $(WORKERS) воркерах (без browser)..."
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser \
		-m "not integration" \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov

test-cov-all: test-up
	@echo "Запуск всех тестов с покрытием..."
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov
	uv run pytest tests/frontend/browser -v --timeout=180 \
		--cov=apps --cov=core --cov-append --cov-report=term-missing --cov-report=html:htmlcov

test-cov-report:
	@echo "Генерация HTML отчета покрытия..."
	uv run coverage html
	@echo "Отчет сохранен в htmlcov/index.html"
