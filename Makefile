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
	@echo "  make test              - Запустить тесты (без интеграционных, 4 воркера)"
	@echo "  make test-all          - Запустить все тесты (включая интеграционные)"
	@echo "  make test WORKERS=8    - Указать число воркеров"

include mk/db.mk
include mk/app.mk
include mk/worker.mk
include mk/sgr.mk
include mk/test.mk
