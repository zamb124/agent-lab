# Python 3.13 — единая версия для всех окружений (dev/test/prod).

# ============================================
# Stage 1: Базовый образ Python 3.13
# ============================================
FROM python:3.13-slim AS base-with-core

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    ffmpeg \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    libreoffice-headless \
    libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# ============================================
# Stage 2: Builder - установка ВСЕХ зависимостей
# ============================================
FROM base-with-core AS builder-all
COPY pyproject.toml README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system \
        --group core \
        --group agents \
        --group worker-base \
        --group rag-worker \
        --group crm \
        --group rag \
        --group sync

# ============================================
# Stage 3: Docs builder (Fumadocs static export)
# ============================================
FROM node:22-bookworm-slim AS docs-builder
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY docs ./docs
COPY scripts/docs_prepare.py ./scripts/
COPY apps/documentation ./apps/documentation
RUN python3 scripts/docs_prepare.py
WORKDIR /app/apps/documentation
RUN npm ci
RUN npm run build
RUN mkdir -p /app/documentation-dist && cp -r out/. /app/documentation-dist/

# ============================================
# Stage 4: Base-final - общий образ со всем кодом
# ============================================
FROM builder-all AS base-final
WORKDIR /app
COPY core/ ./core/
COPY apps/ ./apps/
COPY scripts/ ./scripts/
COPY migrations/ ./migrations/
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# three + 3d-force-graph для CRM графа: apps/crm/main.py монтирует их из repo-root node_modules.
# В образ без этой стадии vendor-URL отдавал index.html (SPA), что ломало загрузку модулей.
FROM node:22-bookworm-slim AS js-vendor
WORKDIR /vendor
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ============================================
# Final stages - отличаются только CMD/EXPOSE
# ============================================

# Agents
FROM base-final AS agents
COPY --from=docs-builder /app/documentation-dist ./documentation-dist
EXPOSE 8001
CMD ["python", "-m", "apps.flows.main"]

# Frontend
FROM base-final AS frontend
EXPOSE 8002
CMD ["python", "-m", "apps.frontend.main"]

# CRM
FROM base-final AS crm
COPY --from=js-vendor /vendor/node_modules/three/build /app/node_modules/three/build
COPY --from=js-vendor /vendor/node_modules/3d-force-graph/dist /app/node_modules/3d-force-graph/dist
EXPOSE 8003
CMD ["python", "-m", "apps.crm.main"]

# RAG
FROM base-final AS rag
EXPOSE 8004
CMD ["python", "-m", "apps.rag.main"]

# Worker
FROM base-final AS worker
CMD ["taskiq", "worker", "apps.flows_worker.worker:worker_app", "--workers", "4"]

# Scheduler
FROM base-final AS scheduler
CMD ["taskiq", "scheduler", "apps.scheduler.scheduler:scheduler"]

# RAG Worker
FROM base-final AS rag-worker
CMD ["taskiq", "worker", "apps.rag_worker.worker:worker_app", "--workers", "2"]

# Sync
FROM base-final AS sync
EXPOSE 8005
CMD ["python", "-m", "apps.sync.main"]

# Sync Worker
FROM base-final AS sync-worker
CMD ["taskiq", "worker", "apps.sync_worker.worker:worker_app", "--workers", "2"]

# Migrations (init container)
FROM base-final AS migrations
CMD ["python", "-m", "scripts.db_migrate", "upgrade"]

# Full (для локальной разработки и тестов)
FROM base-final AS full
COPY --from=docs-builder /app/documentation-dist ./documentation-dist
COPY --from=js-vendor /vendor/node_modules/three/build /app/node_modules/three/build
COPY --from=js-vendor /vendor/node_modules/3d-force-graph/dist /app/node_modules/3d-force-graph/dist
EXPOSE 8001 8002 8003 8004 8005
CMD ["python", "run_prod.py"]
