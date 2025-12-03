.PHONY: test test-all test-up test-down test-cov test-cov-all test-cov-report test-browser test-unit

WORKERS ?= 2

test-up:
	docker-compose up -d postgres
	@echo "Ожидание готовности БД..."
	@sleep 5

test-down:
	docker-compose down

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

# Полный запуск: сначала unit, потом browser
test: test-up
	@echo "=== Запуск unit/API тестов в $(WORKERS) воркерах ==="
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser \
		-m "not integration" || true
	@echo ""
	@echo "=== Запуск browser тестов (последовательно) ==="
	uv run pytest tests/frontend/browser -v --timeout=180 || true
	@$(MAKE) test-down

test-all: test-up
	@echo "=== Запуск всех unit/API тестов в $(WORKERS) воркерах ==="
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser || true
	@echo ""
	@echo "=== Запуск browser тестов (последовательно) ==="
	uv run pytest tests/frontend/browser -v --timeout=180 || true
	@$(MAKE) test-down

test-cov: test-up
	@echo "Запуск тестов с покрытием в $(WORKERS) воркерах (без browser)..."
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser \
		-m "not integration" \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov
	@$(MAKE) test-down

test-cov-all: test-up
	@echo "Запуск всех тестов с покрытием..."
	uv run pytest tests/ -n $(WORKERS) \
		--ignore=tests/frontend/browser \
		--cov=apps --cov=core --cov-report=term-missing --cov-report=html:htmlcov
	uv run pytest tests/frontend/browser -v --timeout=180 \
		--cov=apps --cov=core --cov-append --cov-report=term-missing --cov-report=html:htmlcov
	@$(MAKE) test-down

test-cov-report:
	@echo "Генерация HTML отчета покрытия..."
	uv run coverage html
	@echo "Отчет сохранен в htmlcov/index.html"
