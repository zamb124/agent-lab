.PHONY: build up rebuild down logs clean help docker-build docker-push deploy conf deploy-agents deploy-frontend deploy-crm deploy-worker deploy-rag base stats
.PHONY: dev-up dev-down dev-logs dev-minio-restart dev-bootstrap-postgres test-runner test-runner-down test-runner-unit test-integration prod-up prod-down prod-logs
.PHONY: test-frontend test-rag run-rag check-ui-canon check-i18n build-i18n

# Docker Registry
DOCKER_REGISTRY ?= zambas/repo
# Платформа для сервера (amd64 для большинства VPS)
DOCKER_PLATFORM ?= linux/amd64

# SSH для деплоя и make stats. Имена AGENT_LAB_* — чтобы глобальный export SSH_HOST в шелле
# не перебивал дефолт (у Make переменные из окружения сильнее, чем SSH_HOST ?= в файле).
AGENT_LAB_SSH_USER ?= root
AGENT_LAB_SSH_HOST ?= 84.38.184.105
AGENT_LAB_REMOTE_DIR ?= /opt/agent-lab

# Сборка объединённых JSON переводов на удалённом сервере (stdlib-only скрипт, python:3.13-slim)
_REMOTE_BUILD_I18N = mkdir -p static/i18n && docker run --rm -v $(AGENT_LAB_REMOTE_DIR):/work -w /work python:3.13-slim python scripts/build_i18n.py --output static/i18n

# ============================================================================
# Изолированные окружения (dev/test/prod)
# ============================================================================

# Алиас для удобства
dev: dev-up

# Development Environment (порты: 54321, 63791, 19001-19011)
dev-up:
	@echo "🚀 Запуск Development окружения..."
	docker-compose -f docker-compose-dev.yaml up -d
	@echo "Dev окружение запущено (PostgreSQL: 54321, Redis: 63791, MinIO: 19001/19011)"

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

# Перезапуск только MinIO: при RequestTimeTooSkewed (подпись с хоста vs время в контейнере MinIO)
dev-minio-restart:
	docker-compose -f docker-compose-dev.yaml restart minio
	@echo "MinIO dev перезапущен. Проверка UTC: date -u и docker exec agentlab_minio_dev date -u"

# Недостающие БД на старом томе Postgres: init.sql не перезапускается
dev-bootstrap-postgres:
	docker exec -i agentlab_postgres_dev env PGPASSWORD=admin psql -U platform_user -d postgres < migrations/postgres/bootstrap_idempotent.sql
	@echo "Postgres dev: применён migrations/postgres/bootstrap_idempotent.sql"

# Цели test / test-unit / test-down — в mk/test.mk (после include). Старый one-shot runner:
test-runner:
	@echo "Запуск контейнера tests_runner (docker-compose-test)..."
	docker-compose -f docker-compose-test.yaml up --build --abort-on-container-exit tests_runner
	@echo "Готово."

test-runner-down:
	docker-compose -f docker-compose-test.yaml down -v
	@echo "Compose-test остановлен, volumes удалены."

test-runner-unit:
	docker-compose -f docker-compose-test.yaml run --rm tests_runner pytest tests/ -m unit -v

test-integration:
	@echo "🧪 Запуск integration тестов..."
	docker-compose -f docker-compose-test.yaml run --rm tests_runner pytest tests/ -m integration -v

test-e2e:
	@echo "🧪 Запуск e2e тестов..."
	docker-compose -f docker-compose-test.yaml run --rm tests_runner pytest tests/ -m e2e -v

test-logs:
	docker-compose -f docker-compose-test.yaml logs -f

# Frontend тесты (создание компаний и инициализация агентов)
test-frontend:
	@echo "🧪 Запуск всех frontend тестов..."
	uv run pytest tests/frontend/api/ -v

# Канон UI (apps: без LitElement, без /static/core/lib в импортах JS, без ServiceRegistry)
check-ui-canon:
	@./scripts/check_ui_canon.sh

# JSON переводы ru/en: парсинг и парность имён файлов в корне locales
check-i18n:
	@./scripts/check_i18n.sh

# Сборка объединённых JSON переводов для статической отдачи (dev)
build-i18n:
	uv run python -m scripts.build_i18n

# RAG тесты (с pgvector и MinIO)
test-rag:
	@echo "🧪 Запуск RAG тестов (pgvector + MinIO)..."
	docker-compose -f docker-compose-test.yaml up -d postgres-test redis-test minio-test
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
	ssh $(AGENT_LAB_SSH_USER)@$(AGENT_LAB_SSH_HOST) "cd $(AGENT_LAB_REMOTE_DIR) && git pull && $(_REMOTE_BUILD_I18N) && sudo docker compose pull agents && sudo docker compose up -d agents"

deploy-frontend:
	@echo "Building and deploying frontend..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target frontend -t $(DOCKER_REGISTRY):frontend --load .
	docker push $(DOCKER_REGISTRY):frontend
	ssh $(AGENT_LAB_SSH_USER)@$(AGENT_LAB_SSH_HOST) "cd $(AGENT_LAB_REMOTE_DIR) && git pull && $(_REMOTE_BUILD_I18N) && sudo docker compose pull frontend && sudo docker compose up -d frontend"

deploy-crm:
	@echo "Building and deploying crm..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target crm -t $(DOCKER_REGISTRY):crm --load .
	docker push $(DOCKER_REGISTRY):crm
	ssh $(AGENT_LAB_SSH_USER)@$(AGENT_LAB_SSH_HOST) "cd $(AGENT_LAB_REMOTE_DIR) && git pull && $(_REMOTE_BUILD_I18N) && sudo docker compose pull crm && sudo docker compose up -d crm"

deploy-worker:
	@echo "Building and deploying worker..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target worker -t $(DOCKER_REGISTRY):worker --load .
	docker push $(DOCKER_REGISTRY):worker
	ssh $(AGENT_LAB_SSH_USER)@$(AGENT_LAB_SSH_HOST) "cd $(AGENT_LAB_REMOTE_DIR) && git pull && $(_REMOTE_BUILD_I18N) && sudo docker compose pull taskiq-worker taskiq-scheduler && sudo docker compose up -d taskiq-worker taskiq-scheduler"

deploy-rag:
	@echo "Building and deploying rag..."
	docker buildx build --platform $(DOCKER_PLATFORM) --target rag -t $(DOCKER_REGISTRY):rag --load .
	docker push $(DOCKER_REGISTRY):rag
	ssh $(AGENT_LAB_SSH_USER)@$(AGENT_LAB_SSH_HOST) "cd $(AGENT_LAB_REMOTE_DIR) && git pull && $(_REMOTE_BUILD_I18N) && sudo docker compose pull rag && sudo docker compose up -d rag"

conf:
	@echo "Копирование conf.json на продакшен..."
	scp conf.json $(AGENT_LAB_SSH_USER)@$(AGENT_LAB_SSH_HOST):$(AGENT_LAB_REMOTE_DIR)/conf.json
	@echo "Конфиг скопирован (единый корневой conf.json, слои сервисов внутри services.*)."

# Снимок нагрузки на удалённом хосте (те же AGENT_LAB_* что у деплоя)
stats:
	@echo "Подключение: $(AGENT_LAB_SSH_USER)@$(AGENT_LAB_SSH_HOST) REMOTE_DIR=$(AGENT_LAB_REMOTE_DIR)"
	@SSH_USER="$(AGENT_LAB_SSH_USER)" SSH_HOST="$(AGENT_LAB_SSH_HOST)" REMOTE_DIR="$(AGENT_LAB_REMOTE_DIR)" ./scripts/remote_server_stats.sh || { \
		echo ""; \
		echo "SSH не удался. Переопределите: make stats AGENT_LAB_SSH_HOST=<ip> AGENT_LAB_SSH_USER=<user>"; \
		exit 255; \
	}

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
	@echo "Development (порты: 54321, 63791, 19001-19011):"
	@echo "  make dev-up          - Запустить dev окружение (включая MinIO)"
	@echo "  make dev-down        - Остановить dev окружение"
	@echo "  make dev-logs        - Логи dev окружения"
	@echo "  make dev-clean       - Полная очистка (включая volumes)"
	@echo "  make dev-minio-restart - Перезапуск MinIO (часто убирает RequestTimeTooSkewed при dev на macOS)"
	@echo ""
	@echo "Локальные процессы (без Docker), все сервисы:"
	@echo "  make app             - flows, frontend, crm, rag, sync, workers, scheduler (см. scripts/run.py all)"
	@echo "  make app APP_KILL=1  - то же, сначала kill -9 по PID на портах 8001–8006 (зависший uvicorn)"
	@echo "  MinIO Console (dev): http://localhost:19011 (minioadmin/minioadmin)"
	@echo ""
	@echo "Testing (порты: 54322, 63792, 19002-19012) см. mk/test.mk:"
	@echo "  make test / test-unit / test-down - pytest и test-up (основной поток)"
	@echo "  make test-integration / test-e2e   - через контейнер tests_runner"
	@echo "  make test-runner       - один прогон: up --abort-on-exit tests_runner"
	@echo "  make test-runner-down  - compose-test down -v"
	@echo "  make test-runner-unit  - pytest -m unit в tests_runner"
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
	@echo "  make stats           - SSH: снимок CPU/RAM/диск/Docker/compose на сервере"
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
