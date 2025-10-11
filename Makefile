.PHONY: build up rebuild down logs clean help

build:
	docker-compose build

up:
	docker-compose up -d

rebuild:
	docker-compose up -d --build

down:
	docker-compose down

logs:
	docker-compose logs -f

clean:
	docker-compose down -v

help:
	@echo "Основные команды:"
	@echo "  make build         - Собрать образы"
	@echo "  make up           - Запустить все сервисы"
	@echo "  make down         - Остановить все сервисы"
	@echo "  make logs         - Показать логи всех сервисов"
	@echo "  make clean        - Удалить все (включая volumes)"
	@echo ""
	@echo "Отдельные сервисы:"
	@echo "  make db-up        - Запустить БД"
	@echo "  make db-logs      - Логи БД"
	@echo "  make app-up       - Запустить app"
	@echo "  make app-logs     - Логи app"
	@echo "  make worker-up    - Запустить worker"
	@echo "  make worker-logs  - Логи worker"
	@echo "  make sgr-up       - Запустить sgr"
	@echo "  make sgr-logs     - Логи sgr"
	@echo ""
	@echo "Тесты:"
	@echo "  make test              - Запустить тесты (по умолчанию 4 воркера)"
	@echo "  make test WORKERS=8    - Запустить тесты с указанным числом воркеров"

include mk/db.mk
include mk/app.mk
include mk/worker.mk
include mk/sgr.mk
include mk/test.mk

# Документация
.PHONY: docs-build docs-serve docs-clean

docs-build:
	@echo "📚 Сборка документации..."
	uv run mkdocs build --clean
	@echo "✅ Документация собрана в site/"

docs-serve:
	@echo "📚 Запуск dev-сервера документации на http://127.0.0.1:8000"
	uv run mkdocs serve

docs-clean:
	@echo "🧹 Очистка документации..."
	rm -rf site/
	@echo "✅ Директория site/ удалена"
