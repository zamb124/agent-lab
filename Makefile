.PHONY: help runtime-bootstrap dev dev-up dev-down dev-logs dev-clean dev-minio-restart dev-bootstrap-postgres stress
.PHONY: test-runner test-runner-down test-runner-unit test-integration test-e2e test-logs test-frontend test-rag
.PHONY: check-ui-canon check-i18n check-i18n-keys check-inline-docs check-ui-factories check-command-rest-mirror check-core-frontend-canon check-embed-esm check-events-canon check-logging check-voice-resolver check-speakable-parity check-voice-canon check-field-canon check-rag-post-retrieval-rerank check-company-ai build-i18n
.PHONY: clean-i18n-unused base
.PHONY: render-helm-app-conf require-image-tag k8s-deploy k8s-template k8s-lint k8s-status k8s-logs k8s-rollback k8s-helm-clear-pending k8s-helm-adopt-orphans k8s-secrets-sync k8s-uninstall k8s-health k8s-backup k8s-restore k8s-decommission-compose k8s-cluster-reset

STRESS_NUMERIC_TARGETS := $(shell seq 1 300 2>/dev/null)
STRESS_GOAL_RPS := $(firstword $(filter $(STRESS_NUMERIC_TARGETS),$(MAKECMDGOALS)))
.PHONY: $(STRESS_NUMERIC_TARGETS)

# ============================================================================
# Конфигурация
# ============================================================================

# Базовый образ платформы (используется только при ручных pull/push в Docker Hub)
DOCKER_REGISTRY ?= zambas/repo
DOCKER_PLATFORM ?= linux/amd64

# Helm release
K8S_NAMESPACE ?= platform
K8S_RELEASE ?= agent-lab
HELM_CHART ?= ./deploy/helm/agent-lab
HELM_VALUES ?= $(HELM_CHART)/values.yaml
HELM_VALUES_PROD ?= $(HELM_CHART)/values-prod.yaml
IMAGE_TAG ?=
# Первый helm install (много образов, StatefulSets, hook миграций) часто >15m.
HELM_WAIT_TIMEOUT ?= 30m
PLATFORM_RUNTIME_DIR ?= $(HOME)/.cache/agent-lab/runtimes
PLATFORM_RUNTIME_BIN := $(PLATFORM_RUNTIME_DIR)/bin
export PLATFORM_RUNTIME_DIR
export PATH := $(PLATFORM_RUNTIME_BIN):$(PATH)

runtime-bootstrap:
	@uv run python scripts/bootstrap_runtimes.py

# ============================================================================
# Локальная разработка (без Docker для приложения)
# ============================================================================

dev: dev-up

# Development инфраструктура: postgres :54321, redis :63791, MinIO :19001/19011, Chromium CDP :9222
dev-up: runtime-bootstrap
	@echo "Запуск Development окружения (БД/Redis/MinIO в Docker)..."
	docker-compose -f docker-compose-dev.yaml up -d
	@echo "Dev окружение запущено (PostgreSQL: 54321, Redis: 63791, MinIO: 19001/19011, Chromium CDP: 9222)"

dev-down:
	@echo "Остановка Development окружения..."
	docker-compose -f docker-compose-dev.yaml down

dev-logs:
	docker-compose -f docker-compose-dev.yaml logs -f

dev-clean:
	@echo "Полная очистка Development окружения (включая volumes)..."
	docker-compose -f docker-compose-dev.yaml down -v

# Перезапуск только MinIO: при RequestTimeTooSkewed (подпись с хоста vs время в контейнере MinIO)
dev-minio-restart:
	docker-compose -f docker-compose-dev.yaml restart minio
	@echo "MinIO dev перезапущен. Проверка UTC: date -u и docker exec agentlab_minio_dev date -u"

# Недостающие БД на старом томе Postgres: применить миграции по сервисам.
dev-bootstrap-postgres:
	uv run python -m scripts.db_migrate upgrade
	@echo "Postgres dev: миграции применены через scripts.db_migrate"

stress:
	@SERVICE="$(SERVICE)" PROFILE="$(PROFILE)" URL="$(URL)" TOKEN="$(TOKEN)" RPS="$(or $(RPS),$(STRESS_GOAL_RPS))" RATE="$(RATE)" DURATION="$(DURATION)" PRE_ALLOCATED_VUS="$(PRE_ALLOCATED_VUS)" MAX_VUS="$(MAX_VUS)" STRESS_USE_MOCK="$(STRESS_USE_MOCK)" DRY_RUN="$(DRY_RUN)" ./stress/run.sh

stress-%:
	@SERVICE="$(SERVICE)" PROFILE="$(PROFILE)" URL="$(URL)" TOKEN="$(TOKEN)" RPS="$*" RATE="$(RATE)" DURATION="$(DURATION)" PRE_ALLOCATED_VUS="$(PRE_ALLOCATED_VUS)" MAX_VUS="$(MAX_VUS)" STRESS_USE_MOCK="$(STRESS_USE_MOCK)" DRY_RUN="$(DRY_RUN)" ./stress/run.sh

$(STRESS_NUMERIC_TARGETS):
	@:

# ============================================================================
# Тесты — детали в mk/test.mk
# ============================================================================

# Старый one-shot runner (мигрирует на mk/test.mk полностью).
test-runner:
	@echo "Запуск контейнера tests_runner (docker-compose-test)..."
	docker-compose -f docker-compose-test.yaml up --build --abort-on-container-exit tests_runner

test-runner-down:
	docker-compose -f docker-compose-test.yaml down -v

test-runner-unit:
	docker-compose -f docker-compose-test.yaml run --rm tests_runner pytest tests/ -m unit -v

test-integration:
	@echo "Запуск integration тестов..."
	docker-compose -f docker-compose-test.yaml run --rm tests_runner pytest tests/ -m integration -v

test-e2e:
	@echo "Запуск e2e тестов..."
	docker-compose -f docker-compose-test.yaml run --rm tests_runner pytest tests/ -m e2e -v

test-logs:
	docker-compose -f docker-compose-test.yaml logs -f

# Frontend тесты (создание компаний и инициализация агентов)
test-frontend:
	@echo "Запуск всех frontend тестов..."
	uv run pytest tests/frontend/api/ -v

# RAG тесты (с pgvector и MinIO)
test-rag:
	@echo "Запуск RAG тестов (pgvector + MinIO)..."
	docker-compose -f docker-compose-test.yaml up -d postgres-test redis-test minio-test
	uv run pytest tests/rag/ -v --tb=short

# ============================================================================
# Канон / линты UI / i18n / логирование
# ============================================================================

check-ui-canon:
	@./scripts/check_ui_canon.sh

# Field canon: запрет сырых <input>/<textarea>/<select> в apps/<svc>/ui/{pages,modals,components}/**
# кроме whitelist type= и data-canon (см. scripts/check_field_canon.sh). Не входит в check-events-canon.
check-field-canon:
	@./scripts/check_field_canon.sh

check-logging:
	@./scripts/check_logging_canon.sh

check-ui-factories:
	@uv run python scripts/check_ui_factories.py

check-command-rest-mirror:
	@uv run python scripts/check_command_rest_mirror.py

check-core-frontend-canon:
	@uv run python scripts/check_core_frontend_canon.py
	@uv run python scripts/check_embed_esm_closure.py

check-embed-esm:
	@uv run python scripts/check_embed_esm_closure.py

check-voice-resolver:
	@uv run python scripts/check_voice_resolver_usage.py

check-speakable-parity:
	@uv run python scripts/check_speakable_parity.py

check-tts-pipeline:
	@uv run python scripts/check_tts_pipeline_single_apply.py

check-company-ai:
	uv run python scripts/check_company_ai_canon.py

check-rag-post-retrieval-rerank:
	@uv run python scripts/check_rag_post_retrieval_rerank_single.py

check-voice-canon: check-voice-resolver check-speakable-parity check-tts-pipeline

check-events-canon: check-core-frontend-canon check-ui-canon check-ui-factories check-command-rest-mirror check-voice-resolver check-speakable-parity check-tts-pipeline check-rag-post-retrieval-rerank check-company-ai check-i18n check-i18n-keys
	@echo "check-events-canon: OK"

check-i18n:
	@./scripts/check_i18n.sh

check-i18n-keys:
	@uv run python scripts/check_i18n_keys.py

check-inline-docs:
	@uv run pytest tests/core/test_inline_docs_inventory.py -q

clean-i18n-unused:
	@uv run python scripts/clean_i18n_unused.py --apply

build-i18n:
	uv run python -m scripts.build_i18n

# ============================================================================
# Базовый образ (используется при изменении core зависимостей в Dockerfile.base)
# ============================================================================

base:
	@echo "Сборка и пуш базового образа zambas/agent-lab-base:latest..."
	docker buildx build --platform linux/amd64,linux/arm64 -f Dockerfile.base -t zambas/agent-lab-base:latest --push .

# ============================================================================
# Kubernetes / Helm: деплой и операции
# ============================================================================

# Собрать deploy/helm/agent-lab/files/app-conf.json из корневого conf.json и overlay (канон + K8s-дельты).
render-helm-app-conf:
	uv run python deploy/scripts/render_helm_app_conf.py

require-image-tag:
	@if [ -z "$(strip $(IMAGE_TAG))" ]; then \
	  echo "IMAGE_TAG is required. Use immutable release tag, for example: make k8s-deploy IMAGE_TAG=<sha>"; \
	  exit 1; \
	fi
	@if [ "$(IMAGE_TAG)" = "latest" ]; then \
	  echo "IMAGE_TAG=latest is forbidden for production deploys: it breaks SERVER__DEPLOYMENT_VERSION and PWA static invalidation."; \
	  exit 1; \
	fi

# Локальная валидация чарта (без обращения к кластеру).
k8s-lint: render-helm-app-conf
	helm lint $(HELM_CHART) --set image.tag=lint

# Рендер чарта без apply (для проверки итоговых манифестов).
k8s-template: render-helm-app-conf require-image-tag
	helm template $(K8S_RELEASE) $(HELM_CHART) \
		--namespace $(K8S_NAMESPACE) \
		--values $(HELM_VALUES) \
		--values $(HELM_VALUES_PROD) \
		--set image.tag=$(IMAGE_TAG)

# Применить чарт в текущий kubeconfig-кластер. Атомарно, ждёт rollout.
# Секреты: jq + deploy/scripts/helm_platform_secrets_json.sh → helm --set-json (устойчиво к многострочным значениям).
k8s-deploy: render-helm-app-conf require-image-tag
	@bash -ec '\
	set -euo pipefail; \
	JSON_ARGS=(); \
	if [ -n "$${POSTGRES_PASSWORD:-}" ]; then \
	  JSON_ARGS=(--set-json "platformSecrets=$$(bash deploy/scripts/helm_platform_secrets_json.sh)"); \
	  HELM_WILL_CREATE_PLATFORM_SECRET=1 HELM_RELEASE="$(K8S_RELEASE)" HELM_NAMESPACE="$(K8S_NAMESPACE)" bash deploy/scripts/helm_precheck_install_secret_conflict.sh; \
	fi; \
	helm upgrade --install $(K8S_RELEASE) $(HELM_CHART) \
	  --namespace $(K8S_NAMESPACE) \
	  --create-namespace \
	  --values $(HELM_VALUES) \
	  --values $(HELM_VALUES_PROD) \
	  --set image.tag=$(IMAGE_TAG) \
	  "$${JSON_ARGS[@]}" \
	  --wait --timeout $(HELM_WAIT_TIMEOUT) \
	'

# Снимок состояния кластера: ноды, поды, сервисы, ingress, PVC.
k8s-status:
	@echo "=== Nodes ==="
	@kubectl get nodes -o wide
	@echo ""
	@echo "=== Pods ($(K8S_NAMESPACE)) ==="
	@kubectl get pods -n $(K8S_NAMESPACE) -o wide
	@echo ""
	@echo "=== Services ($(K8S_NAMESPACE)) ==="
	@kubectl get svc -n $(K8S_NAMESPACE)
	@echo ""
	@echo "=== Ingress ($(K8S_NAMESPACE)) ==="
	@kubectl get ingress -n $(K8S_NAMESPACE)
	@echo ""
	@echo "=== PVC ($(K8S_NAMESPACE)) ==="
	@kubectl get pvc -n $(K8S_NAMESPACE)

# Поток логов конкретного Deployment: make k8s-logs SVC=frontend
k8s-logs:
	@if [ -z "$(SVC)" ]; then echo "Usage: make k8s-logs SVC=<deployment-name>"; exit 1; fi
	kubectl logs -n $(K8S_NAMESPACE) deployment/$(SVC) -f --tail=200

# Откат на предыдущую ревизию helm release.
k8s-rollback:
	helm rollback $(K8S_RELEASE) -n $(K8S_NAMESPACE)

# Снять блокировку Helm pending-* без rollback приложений (удалить только зависшие release Secret).
k8s-helm-clear-pending:
	HELM_NAMESPACE=$(K8S_NAMESPACE) HELM_RELEASE=$(K8S_RELEASE) bash deploy/scripts/helm_clear_pending_release.sh

# Adopt orphan-ресурсов в release / удаление legacy перед helm upgrade.
# Решает 'invalid ownership metadata; missing key app.kubernetes.io/managed-by'.
# Параметры: ORPHANS="ingress/foo ingress/bar"  LEGACY="ingress/old"
# Пример:
#   make k8s-helm-adopt-orphans \
#     ORPHANS="ingress/platform-services ingress/platform-frontend" \
#     LEGACY="ingress/platform"
k8s-helm-adopt-orphans:
	HELM_NAMESPACE=$(K8S_NAMESPACE) HELM_RELEASE=$(K8S_RELEASE) \
		bash deploy/scripts/helm_adopt_orphan_resources.sh \
		$(addprefix --delete-legacy=,$(LEGACY)) \
		$(ORPHANS)

# Полное удаление чарта (PVC сохраняются — их удалять вручную).
k8s-uninstall:
	helm uninstall $(K8S_RELEASE) -n $(K8S_NAMESPACE)

# Идемпотентный полный снос legacy docker compose стека на хосте (PROD-ready дисмисс).
# По умолчанию — dry-run (вывод inventory). Реальный снос: CONFIRM=1 make k8s-decommission-compose.
# Целевой хост: SSH_TARGET=root@<host>; default — master (см. _common.sh::MASTER_HOST_IP).
k8s-decommission-compose:
	@bash deploy/scripts/decommission-compose.sh

# Идемпотентный полный reset кластера: helm uninstall + namespace delete + snap remove microk8s --purge.
# По умолчанию — dry-run. Реальный reset: CONFIRM=1 make k8s-cluster-reset.
# После — bootstrap-master.sh + bootstrap-gpu-worker.sh + join-cluster.sh + make k8s-deploy.
k8s-cluster-reset:
	@K8S_NAMESPACE=$(K8S_NAMESPACE) K8S_RELEASE=$(K8S_RELEASE) bash deploy/scripts/cluster-reset.sh

# Полная проверка здоровья кластера (deploy/scripts/cluster-health.sh).
# CHECK_PUBLIC=0 отключает curl-проверки публичных URL (например, в CI без доступа).
k8s-health:
	@CHECK_PUBLIC="$${CHECK_PUBLIC:-1}" PLATFORM_NS=$(K8S_NAMESPACE) bash deploy/scripts/cluster-health.sh

# Бэкап Postgres: backups/dump-<ts>.sql.gz. С S3=s3://... отправляет в Selectel.
k8s-backup:
	@PLATFORM_NS=$(K8S_NAMESPACE) bash deploy/scripts/backup-postgres.sh $(if $(S3),--s3 $(S3),)

# Восстановление: make k8s-restore FILE=backups/dump-...sql.gz [YES=1 — без подтверждения]
k8s-restore:
	@if [ -z "$(FILE)" ]; then echo "Usage: make k8s-restore FILE=<path/to/dump.sql.gz>"; exit 1; fi
	@PLATFORM_NS=$(K8S_NAMESPACE) YES="$${YES:-0}" bash deploy/scripts/restore-postgres.sh $(FILE)

# Обновить Secret platform-secrets через Helm (релиз уже установлен; те же переменные ENV, что для деплоя).
# Запуск: source .env.k8s.secrets && make k8s-secrets-sync
k8s-secrets-sync:
	@if [ -z "$(POSTGRES_PASSWORD)" ] || [ -z "$(AUTH_JWT_SECRET)" ]; then \
		echo "Заполните переменные окружения (POSTGRES_PASSWORD, AUTH_JWT_SECRET, ...). См. deploy/README.md"; \
		exit 1; \
	fi
	@if ! kubectl get ns "$(K8S_NAMESPACE)" >/dev/null 2>&1; then \
		echo "Namespace $(K8S_NAMESPACE) не найден. Сначала: make k8s-deploy (helm создаёт ns через --create-namespace)."; \
		exit 1; \
	fi
	@bash -ec '\
	set -euo pipefail; \
	helm upgrade $(K8S_RELEASE) $(HELM_CHART) \
	  --namespace $(K8S_NAMESPACE) \
	  --reuse-values \
	  --set-json "platformSecrets=$$(bash deploy/scripts/helm_platform_secrets_json.sh)" \
	  --wait --timeout $(HELM_WAIT_TIMEOUT) \
	'

# ============================================================================
# Помощь
# ============================================================================

help:
	@echo "============================================================================"
	@echo "Локальная разработка (Docker для БД/Redis, Python — на хосте):"
	@echo "============================================================================"
	@echo "  make dev-up          - Запустить инфраструктуру (Postgres :54321, Redis :63791, MinIO)"
	@echo "  make dev-down        - Остановить dev"
	@echo "  make dev-logs        - Логи dev"
	@echo "  make dev-clean       - Полная очистка (включая volumes)"
	@echo "  make dev-minio-restart - Перезапуск MinIO (фикс RequestTimeTooSkewed на macOS)"
	@echo ""
	@echo "  make app             - flows, frontend, crm, rag, sync, провайдеры, воркеры (см. mk/app.mk)"
	@echo "  make app APP_KILL=1  - то же, освободив порты 8001-8006/8014 перед запуском"
	@echo ""
	@echo "============================================================================"
	@echo "Тесты:"
	@echo "============================================================================"
	@echo "  make test            - Полный прогон (frontend-core + unit + retry, mk/test.mk)"
	@echo "  make test-unit       - Только unit/API"
	@echo "  make test-rag        - RAG тесты"
	@echo "  make test-frontend   - Frontend API тесты"
	@echo "  make test-down       - Остановить test-стек"
	@echo ""
	@echo "============================================================================"
	@echo "Канон UI / i18n / логирование:"
	@echo "============================================================================"
	@echo "  make check-events-canon - core lib + apps + ui-factories + REST-зеркало + i18n"
	@echo "  make check-embed-esm   - автономный embed: замыкание импортов без bare lit/@platform"
	@echo "  make check-i18n         - JSON ru/en парность"
	@echo "  make check-i18n-keys    - Cross-check код ↔ JSON"
	@echo "  make check-logging      - Канон structlog, get_logger, контракт"
	@echo ""
	@echo "============================================================================"
	@echo "Миграции БД:"
	@echo "============================================================================"
	@echo "  make migrate                      - Применить миграции для всех сервисов"
	@echo "  make migrate-new m=\"...\" s=shared - Создать новую autogenerate ревизию"
	@echo "  make migrate-empty m=\"...\" s=crm  - Создать пустую ревизию"
	@echo ""
	@echo "============================================================================"
	@echo "Kubernetes / Helm деплой (см. deploy/README.md и deploy/cluster-setup.md):"
	@echo "============================================================================"
	@echo "  make render-helm-app-conf - conf.json + overlay -> files/app-conf.json"
	@echo "  make k8s-lint            - helm lint чарта"
	@echo "  make k8s-template        - Рендер всех манифестов в stdout (без apply)"
	@echo "  make k8s-deploy          - helm upgrade --install (--wait, timeout=$(HELM_WAIT_TIMEOUT))"
	@echo "  make k8s-deploy IMAGE_TAG=<sha> HELM_WAIT_TIMEOUT=45m - долгий первый install"
	@echo "  make k8s-status          - Снимок: nodes, pods, svc, ingress, pvc"
	@echo "  make k8s-logs SVC=frontend - Логи Deployment frontend"
	@echo "  make k8s-rollback        - helm rollback на предыдущую ревизию"
	@echo "  make k8s-helm-clear-pending - снять pending-upgrade/install/rollback у Helm (не откат Pod)"
	@echo "  make k8s-secrets-sync    - Обновить Secret platform-secrets через helm (--reuse-values)"
	@echo "  make k8s-uninstall       - helm uninstall (PVC сохраняются)"
	@echo "  make k8s-health          - Полная проверка кластера (deploy/scripts/cluster-health.sh)"
	@echo "  make k8s-backup [S3=s3://...] - pg_dumpall в backups/ (опционально в Selectel S3)"
	@echo "  make k8s-restore FILE=<path>  - Восстановление дампа в pod postgres-0"
	@echo ""
	@echo "============================================================================"
	@echo "Документация (Zensical):"
	@echo "============================================================================"
	@echo "  make doc        - docs_prepare + zensical RU/EN build → documentation-dist/"
	@echo "  make doc-serve  - docs_prepare + zensical serve (локальный предпросмотр)"
	@echo "  make doc-clean  - Удалить собранную документацию"
	@echo "  make test-ui-doc - test-ui затем make doc"

include mk/app.mk
include mk/test.mk
include mk/migrate.mk

# Документация
.PHONY: doc doc-serve doc-docker doc-clean docs-build docs-serve docs-clean docs-docker-build

doc:
	@echo "Локальная сборка документации (Zensical RU + EN)..."
	rm -rf documentation-dist build/documentation-ru build/documentation-en build/zensical-en-out
	uv run python scripts/extract_openapi.py
	uv run python scripts/docs_prepare.py
	uv run python scripts/check_docs_locale_parity.py
	uv run --group docs zensical build --clean --config-file zensical.ru.toml
	uv run --group docs zensical build --clean --config-file zensical.en.toml
	mkdir -p documentation-dist/en
	cp -a build/zensical-en-out/. documentation-dist/en/
	uv run python scripts/docs_postprocess.py
	uv run python scripts/check_docs_locale_parity.py --site documentation-dist
	@echo "Документация: documentation-dist/ и documentation-dist/en/ (монтирование /documentation/)"

doc-serve:
	@echo "Предпросмотр RU-сайта: docs_prepare + zensical serve (zensical.ru.toml)"
	uv run python scripts/docs_prepare.py
	uv run --group docs zensical serve --config-file zensical.ru.toml

doc-docker:
	docker build --target docs-builder -t agent-lab-docs .
	@echo "Образ agent-lab-docs; статика в контейнере: /app/documentation-dist/"

doc-clean:
	@echo "Очистка артефактов документации..."
	rm -rf documentation-dist/ build/documentation-ru build/documentation-en build/zensical-en-out site/ .cache

# Алиасы для обратной совместимости
docs-build: doc
docs-serve: doc-serve
docs-docker-build: doc-docker
docs-clean: doc-clean
