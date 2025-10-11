.PHONY: test test-all test-up test-down

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

