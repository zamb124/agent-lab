# Упрощённый Dockerfile
# Базовый образ zambas/agent-lab-base содержит:
#   - Python 3.12
#   - Core + worker-base зависимости
#   - Torch CPU-only
#   - Системные пакеты: curl, tesseract, poppler, libgl1, libglib2.0-0

# ============================================
# Stage 1: Базовый образ
# ============================================
FROM zambas/agent-lab-base:latest AS base-with-core

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
# Stage 3: Docs builder (для сборки документации)
# ============================================
FROM python:3.12-slim AS docs-builder
RUN pip install uv
WORKDIR /app

RUN uv pip install --system \
    "mkdocs>=1.6.1" \
    "mkdocs-material>=9.6.21" \
    "mkdocs-static-i18n>=1.3.0" \
    "pymdown-extensions>=10.16.1"

COPY mkdocs.yml ./
COPY docs/ ./docs/ 
COPY core/ ./core/
COPY apps/ ./apps/

RUN mkdocs build --clean

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

# ============================================
# Final stages - отличаются только CMD/EXPOSE
# ============================================

# Agents
FROM base-final AS agents
COPY --from=docs-builder /app/site ./apps/agents/site
EXPOSE 8001
CMD ["python", "-m", "apps.flows.main"]

# Frontend
FROM base-final AS frontend
EXPOSE 8002
CMD ["python", "-m", "apps.frontend.main"]

# CRM
FROM base-final AS crm
EXPOSE 8003
CMD ["python", "-m", "apps.crm.main"]

# RAG
FROM base-final AS rag
EXPOSE 8004
CMD ["python", "-m", "apps.rag.main"]

# Worker
FROM base-final AS worker
CMD ["taskiq", "worker", "apps.broker.worker:broker", "--workers", "4"]

# Scheduler
FROM base-final AS scheduler
CMD ["taskiq", "scheduler", "apps.scheduler.scheduler:scheduler"]

# RAG Worker
FROM base-final AS rag-worker
CMD ["taskiq", "worker", "apps.rag_worker.worker:broker", "--workers", "2"]

# Sync
FROM base-final AS sync
EXPOSE 8005
CMD ["python", "-m", "apps.sync.main"]

# Sync Worker
FROM base-final AS sync-worker
CMD ["taskiq", "worker", "apps.sync_worker.worker:broker", "--workers", "2"]

# Migrations (init container)
FROM base-final AS migrations
CMD ["python", "-m", "scripts.db_migrate", "upgrade"]

# Full (для локальной разработки и тестов)
FROM base-final AS full
COPY --from=docs-builder /app/site ./site
EXPOSE 8001 8002 8003 8004 8005
CMD ["python", "run_prod.py"]
