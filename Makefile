.PHONY: build up rebuild down logs clean help docker-build docker-push deploy conf deploy-agents deploy-frontend deploy-crm deploy-worker deploy-rag base
.PHONY: dev-up dev-down dev-logs test test-down test-unit test-integration prod-up prod-down prod-logs
.PHONY: test-frontend test-rag run-rag

# Docker Registry
DOCKER_REGISTRY ?= zambas/repo
# Платформа для сервера (amd64 для большинства VPS)
DOCKER_PLATFORM ?= linux/amd64

# SSH настройки для деплоя
SSH_USER ?= zambas124
SSH_HOST ?= 46.21.244.79
REMOTE_DIR ?= /opt/agents-lab

# ============================================================================
# Изолированные окружения (dev/test/prod)
# ============================================================================

# Алиас для удобства
dev: dev-up

# Development Environment (порты: 5435, 6381, 9000-9001)
dev-up:
	@echo "🚀 Запуск Development окружения..."
	docker-compose -f docker-compose-dev.yaml up -d
	@echo "✅ Dev окружение запущено (PostgreSQL: 5435, Redis: 6381, MinIO: 9000/9001)"

dev-down:
	@echo "🛑 Остановка Development окружения..."
	docker-compose -f docker-compose-dev.yaml down
	@echo "✅ Dev окружение остановлено"

dev-logs:
	docker-compose -f docker-compose-dev.yaml logs -f

dev-clean:
	@echo "🧹 Полная очистка Development окружения (включая volumes)..."
	docker-compose -f docker-compose-dev.yaml down -v
	@echo "✅ Dev окружение очищено"

# Test Environment (порты: 5434, 6380, 9002-9003, 8005 для test-a2a-agent) - ТОЛЬКО для автотестов
test:
	@echo "🧪 Запуск тестов в изолированном окружении (включая MinIO и test-a2a-agent)..."
	docker-compose -f docker-compose-test.yaml up --build --abort-on-container-exit tests-runner
	@echo "✅ Тесты завершены"

test-down:
	@echo "🛑 Остановка Test окружения..."
	docker-compose -f docker-compose-test.yaml down -v
	@echo "✅ Test окружение остановлено и очищено"

test-unit:
	@echo "🧪 Запуск unit тестов..."
	docker-compose -f docker-compose-test.yaml run --rm tests-runner pytest tests/ -m unit -v

test-integration:
	@echo "🧪 Запуск integration тестов..."
	docker-compose -f docker-compose-test.yaml run --rm tests-runner pytest tests/ -m integration -v

test-e2e:
	@echo "🧪 Запуск e2e тестов..."
	docker-compose -f docker-compose-test.yaml run --rm tests-runner pytest tests/ -m e2e -v

test-logs:
	docker-compose -f docker-compose-test.yaml logs -f

# Frontend тесты (создание компаний и инициализация агентов)
test-frontend:
	@echo "🧪 Запуск всех frontend тестов..."
	uv run pytest tests/frontend/api/ -v

# RAG тесты (с реальным ChromaDB и MinIO)
test-rag:
	@echo "🧪 Запуск RAG тестов (ChromaDB + MinIO)..."
	docker-compose -f docker-compose-test.yaml up -d postgres-test redis-test chroma-test minio-test
	@echo "🚀 Запуск тестов..."
	uv run pytest tests/rag/ -v --tb=short
	@echo "✅ RAG тесты завершены"

# Production Environment (стандартные порты: 5432, 6379)
prod-up:
	@echo "🚀 Запуск Production окружения..."
	docker-compose -f docker-compose-prod.yaml up -d
	@echo "✅ Prod окружение запущено"

prod-down:
	@echo "🛑 Остановка Production окружения..."
	docker-compose -f docker-compose-prod.yaml down
	@echo "✅ Prod окружение остановлено"

prod-logs:
	docker-compose -f docker-compose-prod.yaml logs -f

prod-build:
	@echo "🏗️  Сборка Production образов..."
	docker-compose -f docker-compose-prod.yaml build --pull
	@echo "✅ Образы собраны"

prod-restart:
	@echo "🔄 Перезапуск Production окружения..."
	docker-compose -f docker-compose-prod.yaml restart
	@echo "✅ Сервисы перезапущены"

# ============================================================================
# Старые команды (используют docker-compose.yml)
# ============================================================================

build:
	docker-compose build

# Пересборка и пуш базового образа (при изменении core зависимостей)
base:
	@echo "🔧 Сборка и пуш базового образа zambas/agent-lab-base:latest..."
	docker buildx build --platform linux/amd64,linux/arm64 -f Dockerfile.base -t zambas/agent-lab-base:latest --push .
	@echo "✅ Базовый образ zambas/agent-lab-base:latest обновлён"

docker-build:
	@echo "Building Docker images for $(DOCKER_PLATFORM)..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target agents -t $(DOCKER_REGISTRY):agents --load .
	docker buildx build --platform $(DOCKER_PLATFORM) --target frontend -t $(DOCKER_REGISTRY):frontend --load .
	docker buildx build --platform $(DOCKER_PLATFORM) --target crm -t $(DOCKER_REGISTRY):crm --load .
	docker buildx build --platform $(DOCKER_PLATFORM) --target worker -t $(DOCKER_REGISTRY):worker --load .
	@echo "Done! Images built for $(DOCKER_PLATFORM)."

docker-push:
	@echo "Pushing images to $(DOCKER_REGISTRY)..."
	docker push $(DOCKER_REGISTRY):agents
	docker push $(DOCKER_REGISTRY):frontend
	docker push $(DOCKER_REGISTRY):crm
	docker push $(DOCKER_REGISTRY):worker
	@echo "Done! Images pushed to Docker Hub."

deploy: docker-build docker-push
	@echo "Running deploy script..."
	./deploy/deploy.sh

deploy-fast:
	@echo "Deploy without rebuild (just pull from registry)..."
	./deploy/deploy.sh

# Деплой отдельных сервисов
deploy-agents:
	@echo "Building and deploying agents..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target agents -t $(DOCKER_REGISTRY):agents --load .
	docker push $(DOCKER_REGISTRY):agents
	ssh $(SSH_USER)@$(SSH_HOST) "cd $(REMOTE_DIR) && git pull && sudo docker compose pull agents && sudo docker compose up -d agents"

deploy-frontend:
	@echo "Building and deploying frontend..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target frontend -t $(DOCKER_REGISTRY):frontend --load .
	docker push $(DOCKER_REGISTRY):frontend
	ssh $(SSH_USER)@$(SSH_HOST) "cd $(REMOTE_DIR) && git pull && sudo docker compose pull frontend && sudo docker compose up -d frontend"

deploy-crm:
	@echo "Building and deploying crm..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target crm -t $(DOCKER_REGISTRY):crm --load .
	docker push $(DOCKER_REGISTRY):crm
	ssh $(SSH_USER)@$(SSH_HOST) "cd $(REMOTE_DIR) && git pull && sudo docker compose pull crm && sudo docker compose up -d crm"

deploy-worker:
	@echo "Building and deploying worker..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target worker -t $(DOCKER_REGISTRY):worker --load .
	docker push $(DOCKER_REGISTRY):worker
	ssh $(SSH_USER)@$(SSH_HOST) "cd $(REMOTE_DIR) && git pull && sudo docker compose pull taskiq-worker taskiq-scheduler && sudo docker compose up -d taskiq-worker taskiq-scheduler"

deploy-rag:
	@echo "Building and deploying rag..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target rag -t $(DOCKER_REGISTRY):rag --load .
	docker push $(DOCKER_REGISTRY):rag
	ssh $(SSH_USER)@$(SSH_HOST) "cd $(REMOTE_DIR) && git pull && sudo docker compose pull rag && sudo docker compose up -d rag"

conf:
	@echo "Копирование conf.json на продакшен..."
	scp conf.json $(SSH_USER)@$(SSH_HOST):$(REMOTE_DIR)/conf.json
	scp apps/agents/conf.json $(SSH_USER)@$(SSH_HOST):$(REMOTE_DIR)/apps/agents/conf.json
	scp apps/frontend/conf.json $(SSH_USER)@$(SSH_HOST):$(REMOTE_DIR)/apps/frontend/conf.json
	scp apps/crm/conf.json $(SSH_USER)@$(SSH_HOST):$(REMOTE_DIR)/apps/crm/conf.json
	scp apps/rag/conf.json $(SSH_USER)@$(SSH_HOST):$(REMOTE_DIR)/apps/rag/conf.json
	@echo "Конфиги скопированы!"

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
	@echo "============================================================================"
	@echo "Изолированные окружения (dev/test/prod):"
	@echo "============================================================================"
	@echo "Development (порты: 5435, 6381, 9000-9001):"
	@echo "  make dev-up          - Запустить dev окружение (включая MinIO)"
	@echo "  make dev-down        - Остановить dev окружение"
	@echo "  make dev-logs        - Логи dev окружения"
	@echo "  make dev-clean       - Полная очистка (включая volumes)"
	@echo "  MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
	@echo ""
	@echo "Testing (порты: 5434, 6380, 9002-9003) - ТОЛЬКО для автотестов:"
	@echo "  make test            - Запустить все тесты (включая MinIO)"
	@echo "  make test-unit       - Запустить unit тесты"
	@echo "  make test-integration - Запустить integration тесты"
	@echo "  make test-e2e        - Запустить e2e тесты"
	@echo "  make test-down       - Остановить и очистить test окружение"
	@echo ""
	@echo "Frontend тесты (создание компаний и агентов):"
	@echo "  make test-frontend   - Все frontend тесты"
	@echo ""
	@echo "Production (стандартные порты: 5432, 6379):"
	@echo "  make prod-up         - Запустить prod окружение"
	@echo "  make prod-down       - Остановить prod окружение"
	@echo "  make prod-logs       - Логи prod окружения"
	@echo "  make prod-build      - Собрать prod образы"
	@echo "  make prod-restart    - Перезапустить сервисы"
	@echo ""
	@echo "============================================================================"
	@echo "Деплой (Docker Hub):"
	@echo "============================================================================"
	@echo "  make base            - Пересобрать и запушить базовый образ (при изменении core)"
	@echo "  make deploy          - Полный деплой (build + push + deploy.sh)"
	@echo "  make deploy-fast     - Быстрый деплой (только pull с registry, без сборки)"
	@echo "  make deploy-agents   - Деплой только agents"
	@echo "  make deploy-frontend - Деплой только frontend"
	@echo "  make deploy-crm      - Деплой только crm"
	@echo "  make deploy-worker   - Деплой только worker"
	@echo "  make conf            - Скопировать conf.json на продакшен (секреты)"
	@echo "  make docker-build    - Только собрать образы локально"
	@echo "  make docker-push     - Только запушить образы в Docker Hub"
	@echo ""
	@echo "============================================================================"
	@echo "Основные команды (старые, используют docker-compose.yml):"
	@echo "============================================================================"
	@echo "  make build         - Собрать образы (docker-compose)"
	@echo "  make prod          - Git pull, prune, build --pull, up -d (прод-запуск)"
	@echo "  make up            - Запустить все сервисы"
	@echo "  make down          - Остановить все сервисы"
	@echo "  make logs          - Показать логи всех сервисов"
	@echo "  make clean         - Удалить все (включая volumes)"
	@echo ""
	@echo "Документация (MkDocs):"
	@echo "  make doc-docker - Полная сборка в Docker (agents + API docs + MkDocs)"
	@echo "  make doc        - Собрать MkDocs (без генерации API)"
	@echo "  make doc-serve  - Запустить dev-сервер (http://127.0.0.1:8000)"
	@echo "  make doc-clean  - Удалить собранную документацию"

run-rag:
	@echo "🚀 Запуск RAG сервиса..."
	uv run python scripts/run_rag.py

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
