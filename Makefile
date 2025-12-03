.PHONY: build up rebuild down logs clean help docker-build docker-push deploy

# Docker Registry
DOCKER_REGISTRY ?= zambas/repo
# Платформа для сервера (amd64 для большинства VPS)
DOCKER_PLATFORM ?= linux/amd64

build:
	docker-compose build

docker-build:
	@echo "Building Docker images for $(DOCKER_PLATFORM)..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target agents -t $(DOCKER_REGISTRY):agents --load .
	docker buildx build --platform $(DOCKER_PLATFORM) --target frontend -t $(DOCKER_REGISTRY):frontend --load .
	docker buildx build --platform $(DOCKER_PLATFORM) --target worker -t $(DOCKER_REGISTRY):worker --load .
	@echo "Done! Images built for $(DOCKER_PLATFORM)."

docker-push:
	@echo "Pushing images to $(DOCKER_REGISTRY)..."
	docker push $(DOCKER_REGISTRY):agents
	docker push $(DOCKER_REGISTRY):frontend
	docker push $(DOCKER_REGISTRY):worker
	@echo "Done! Images pushed to Docker Hub."

deploy: docker-build docker-push
	@echo "Running deploy script..."
	./deploy/deploy.sh

deploy-fast:
	@echo "Deploy without rebuild (just pull from registry)..."
	./deploy/deploy.sh

deploy-code: docker-build docker-push
	@echo "Deploy with code changes (uses Docker cache for deps)..."
	./deploy/deploy.sh

prod:
	@echo "🔄 Обновление репозитория (git pull)..."
	@git pull --rebase --autostash
	@echo "🛑 Остановка текущих контейнеров..."
	docker-compose down
	@echo "🧹 Очистка висячих образов и builder cache..."
	docker image prune -f
	docker builder prune -f
	@echo "🏗️  Сборка образов (pull базовых образов)..."
	docker-compose build --pull
	@echo "🚀 Запуск сервисов в фоне..."
	docker-compose up -d
	@echo "🧽 Финальная очистка висячих образов..."
	docker image prune -f
	@echo "✅ Прод-запуск завершён"

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
	@echo "Деплой (Docker Hub):"
	@echo "  make deploy        - Полный деплой (build + push + deploy.sh)"
	@echo "  make deploy-fast   - Быстрый деплой (только pull с registry, без сборки)"
	@echo "  make deploy-code   - Деплой с изменениями кода (Docker cache для deps)"
	@echo "  make docker-build  - Только собрать образы локально"
	@echo "  make docker-push   - Только запушить образы в Docker Hub"
	@echo ""
	@echo "Основные команды:"
	@echo "  make build         - Собрать образы (docker-compose)"
	@echo "  make prod          - Git pull, prune, build --pull, up -d (прод-запуск)"
	@echo "  make up            - Запустить все сервисы"
	@echo "  make down          - Остановить все сервисы"
	@echo "  make logs          - Показать логи всех сервисов"
	@echo "  make clean         - Удалить все (включая volumes)"
	@echo ""
	@echo "Отдельные сервисы:"
	@echo "  make db-up        - Запустить БД"
	@echo "  make db-logs      - Логи БД"
	@echo "  make app-up       - Запустить app"
	@echo "  make app-logs     - Логи app"
	@echo "  make worker-up    - Запустить worker (старый)"
	@echo "  make worker-logs  - Логи worker"
	@echo ""
	@echo "TaskIQ Worker (новый):"
	@echo "  make taskiq       - Запустить TaskIQ worker локально"
	@echo "  make taskiq-reload - TaskIQ worker с hot reload"
	@echo "  make taskiq-prod  - TaskIQ worker с 4 воркерами"
	@echo "  make sgr-up       - Запустить sgr"
	@echo "  make sgr-logs     - Логи sgr"
	@echo ""
	@echo "Миграции:"
	@echo "  make remigrate COMPANY=<id>  - Перемигрировать компанию (тулы и flows)"
	@echo ""
	@echo "Документация (MkDocs):"
	@echo "  make doc-docker - Полная сборка в Docker (agents + API docs + MkDocs)"
	@echo "  make doc        - Собрать MkDocs (без генерации API)"
	@echo "  make doc-serve  - Запустить dev-сервер (http://127.0.0.1:8000)"
	@echo "  make doc-clean  - Удалить собранную документацию"
	@echo ""
	@echo "Тесты:"
	@echo "  make test              - Запустить тесты (по умолчанию 4 воркера)"
	@echo "  make test WORKERS=8    - Запустить тесты с указанным числом воркеров"

include mk/db.mk
include mk/app.mk
include mk/worker.mk
include mk/sgr.mk
include mk/test.mk
include mk/migrate.mk

# Документация
.PHONY: doc doc-serve doc-docker doc-clean docs-build docs-serve docs-clean docs-docker-build

# Короткие алиасы
doc:
	@echo "Локальная сборка документации..."
	uv run mkdocs build --clean
	@echo "Документация собрана в site/"

doc-serve:
	@echo "📚 Запуск dev-сервера документации на http://127.0.0.1:8000"
	uv run mkdocs serve

doc-docker:
	@echo "Сборка документации в Docker (полный цикл)..."
	@echo "1. Запуск agents сервиса..."
	docker-compose up -d agents
	@echo "2. Ожидание готовности сервиса..."
	@sleep 5
	@echo "3. Генерация API документации..."
	docker-compose --profile docs run --rm docs-generator
	@echo "4. Сборка MkDocs..."
	docker build -t agent-lab-docs --target docs-builder .
	docker create --name temp-docs agent-lab-docs
	docker cp temp-docs:/app/site ./site
	docker rm temp-docs
	@echo "Документация собрана в site/"

doc-clean:
	@echo "🧹 Очистка документации..."
	rm -rf site/
	@echo "✅ Директория site/ удалена"

# Полные имена (для обратной совместимости)
docs-build: doc
docs-serve: doc-serve
docs-docker-build: doc-docker
docs-clean: doc-clean
