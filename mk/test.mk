.PHONY: test test-all test-up test-down test-cov test-cov-all test-cov-report

WORKERS ?= 4

test-up:
	docker-compose up -d postgres
	@echo "Ожидание готовности БД..."
	@sleep 5

test-down:
	docker-compose down

test: test-up
	@echo "Запуск тестов в $(WORKERS) воркерах (без интеграционных)..."
	uv run pytest tests/ -n $(WORKERS) -m "not integration"
	@$(MAKE) test-down

test-all: test-up
	@echo "Запуск всех тестов в $(WORKERS) воркерах (включая интеграционные)..."
	uv run pytest tests/ -n $(WORKERS)
	@$(MAKE) test-down

test-cov: test-up
	@echo "Запуск тестов с покрытием в $(WORKERS) воркерах (без интеграционных)..."
	uv run pytest tests/ -n $(WORKERS) -m "not integration" --cov=app --cov-report=term-missing --cov-report=html:htmlcov
	@$(MAKE) test-down

test-cov-all: test-up
	@echo "Запуск всех тестов с покрытием в $(WORKERS) воркерах (включая интеграционные)..."
	uv run pytest tests/ -n $(WORKERS) --cov=app --cov-report=term-missing --cov-report=html:htmlcov
	@$(MAKE) test-down

test-cov-report:
	@echo "Генерация HTML отчета покрытия..."
	uv run coverage html
	@echo "Отчет сохранен в htmlcov/index.html"

