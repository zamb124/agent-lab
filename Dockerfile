# Python 3.14t (free-threaded, PEP 779) + Granian. Единая версия для всех окружений
# (dev/test/prod). Всё тяжёлое (apt-runtime, Node/Go/.NET, /opt/venv с torch + ML
# deps + FastAPI + Granian) предсобрано в `ghcr.io/zamb124/agent-lab-base:latest`
# через workflow `.github/workflows/build-base.yml`. Сам main Dockerfile делает
# только COPY кода — CI build за минуты, не за час.
#
# Когда пересобирается base: автоматически в CI при изменении pyproject.toml /
# uv.lock / Dockerfile.base в main, либо вручную через Actions UI.

# ============================================
# Этап 1: базовый образ (предсобранный, содержит весь Python-стек)
# ============================================
ARG BASE_IMAGE=ghcr.io/zamb124/agent-lab-base:latest
FROM ${BASE_IMAGE} AS base-with-core

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Алиас стадии для совместимости с историческими ссылками (base-final FROM builder-all).
FROM base-with-core AS builder-all

# ============================================
# Этап 4: base-final - общий образ со всем кодом
# ============================================
FROM builder-all AS base-final
WORKDIR /app
COPY core/ ./core/
COPY apps/ ./apps/
COPY scripts/ ./scripts/
COPY migrations/ ./migrations/
COPY conf/ ./conf/
COPY tests/ui/design-system/catalog.yaml ./tests/ui/design-system/catalog.yaml
COPY tests/ui/design-system/components ./tests/ui/design-system/components

# UI-бандлы: tsc (strict) и esbuild per-app → apps/<svc>/ui-dist/. В образ уходит
# только скомпилированный вывод — браузер грузит index.js + hashed chunks,
# mount отдаёт ui-dist (core/app/spa.py).
FROM node:26-bookworm-slim AS ui-builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsconfig.base.json ./
COPY scripts/build/ui.ts ./scripts/build/ui.ts
COPY core/frontend/static ./core/frontend/static
COPY tests/ui/design-system/components ./tests/ui/design-system/components
COPY apps/ ./apps/
RUN npm run typecheck:ui \
    && npm run build:ui \
    && for d in apps/*/ui-dist; do mkdir -p "/out/$d" && cp -a "$d/." "/out/$d/"; done \
    && mkdir -p /out/core/frontend && cp -a core/frontend/embed-dist /out/core/frontend/embed-dist

# ============================================
# Сборщик документации (статический сайт Zensical), после ui-builder —
# esbuild для docs/javascripts приезжает из его node_modules.
# ============================================
# Docs-builder отдельный, GIL-build cp314: статический HTML, free-threading не нужен,
# а часть deps zensical тянет Rust-extension'ы без cp314t wheels.
FROM python:3.14-slim AS docs-builder
RUN pip install --no-cache-dir "zensical>=0.0.73"
WORKDIR /app
ENV PYTHONPATH=/app
# esbuild — статические Go-бинари из ui-builder стейджа (без node-рантайма)
COPY --from=ui-builder /app/node_modules/@esbuild ./node_modules/@esbuild
COPY zensical.ru.toml zensical.en.toml ./
COPY docs ./docs
COPY core/frontend/static/assets/service_logos/frontend_logo.svg ./core/frontend/static/assets/service_logos/frontend_logo.svg
COPY scripts/__init__.py ./scripts/__init__.py
COPY scripts/docs ./scripts/docs
RUN python -m scripts.docs.prepare && \
    zensical build --clean --config-file zensical.ru.toml && \
    zensical build --clean --config-file zensical.en.toml && \
    mkdir -p documentation-dist/en && \
    cp -a build/zensical-en-out/. documentation-dist/en/

# ============================================
# Финальные стадии - отличаются только CMD/EXPOSE
# ============================================

# Flows
FROM base-final AS agents
COPY --from=docs-builder /app/documentation-dist ./documentation-dist
EXPOSE 8001
CMD ["granian", "--interface", "asgi", "apps.flows.main:app", "--host", "0.0.0.0", "--port", "8001", "--http", "auto", "--ws"]

# Frontend
FROM base-final AS frontend
EXPOSE 8002
CMD ["granian", "--interface", "asgi", "apps.frontend.main:app", "--host", "0.0.0.0", "--port", "8002", "--http", "auto", "--ws"]

# CRM
FROM base-final AS crm
EXPOSE 8003
CMD ["granian", "--interface", "asgi", "apps.crm.main:app", "--host", "0.0.0.0", "--port", "8003", "--http", "auto", "--ws"]

# RAG
FROM base-final AS rag
EXPOSE 8004
CMD ["granian", "--interface", "asgi", "apps.rag.main:app", "--host", "0.0.0.0", "--port", "8004", "--http", "auto", "--ws"]

# Flows worker (TaskIQ — Granian не применим)
FROM base-final AS worker
CMD ["taskiq", "worker", "apps.flows.worker:worker_app", "--workers", "4"]

# Scheduler
FROM base-final AS scheduler
CMD ["taskiq", "scheduler", "apps.scheduler.scheduler:scheduler"]

# RAG Worker
FROM base-final AS rag-worker
CMD ["taskiq", "worker", "apps.rag.worker:worker_app", "--workers", "2"]

# Sync
FROM base-final AS sync
EXPOSE 8005
CMD ["granian", "--interface", "asgi", "apps.sync.main:app", "--host", "0.0.0.0", "--port", "8005", "--http", "auto", "--ws"]

# Sync Worker
FROM base-final AS sync-worker
CMD ["taskiq", "worker", "apps.sync.worker:worker_app", "--workers", "2"]

# Capability Gateway
FROM base-final AS capability-gateway
EXPOSE 8016
CMD ["granian", "--interface", "asgi", "apps.capability_gateway.main:app", "--host", "0.0.0.0", "--port", "8016", "--http", "auto", "--ws"]

# Python Code Runner
FROM base-final AS code-runner-python
EXPOSE 8017
CMD ["granian", "--interface", "asgi", "apps.code_runner_python.main:app", "--host", "0.0.0.0", "--port", "8017", "--http", "auto", "--ws"]

# Node Code Runner
FROM base-final AS code-runner-node
EXPOSE 8018
CMD ["granian", "--interface", "asgi", "apps.code_runner_node.main:app", "--host", "0.0.0.0", "--port", "8018", "--http", "auto", "--ws"]

# Go Code Runner
FROM base-final AS code-runner-go
EXPOSE 8019
CMD ["granian", "--interface", "asgi", "apps.code_runner_go.main:app", "--host", "0.0.0.0", "--port", "8019", "--http", "auto", "--ws"]

# C# Code Runner
FROM base-final AS code-runner-csharp
EXPOSE 8020
CMD ["granian", "--interface", "asgi", "apps.code_runner_csharp.main:app", "--host", "0.0.0.0", "--port", "8020", "--http", "auto", "--ws"]

# Migrations (init container)
FROM base-final AS migrations
CMD ["python", "-m", "scripts.db.migrate", "upgrade"]

# Full — production target для CI/CD (build-push-action target=full).
# Один immutable образ для всех 15 application Deployment'ов + 5 TaskIQ workers
# + db-migrate init container. Конкретная команда задаётся через `command:`
# в values.yaml (granian-CLI с per-service флагами и static-path-mount).
# Включает docs-builder артефакт и собранные UI-бандлы (npm lazy-чанки —
# внутри apps/<svc>/ui-dist/chunks/).
FROM base-final AS full
COPY --from=docs-builder /app/documentation-dist ./documentation-dist
COPY --from=ui-builder /out/apps/ ./apps/
COPY --from=ui-builder /out/core/frontend/embed-dist ./core/frontend/embed-dist
EXPOSE 8001 8002 8003 8004 8005 8006 8008 8009 8010 8015 8016 8017 8018 8019 8020
