# Python 3.13 — единая версия для всех окружений (dev/test/prod).

# ============================================
# Этап 1: базовый образ Python 3.13
# ============================================
FROM python:3.13-slim AS base-with-core

ARG NODE_MAJOR=24
ARG GO_VERSION=1.26.1
ARG DOTNET_CHANNEL=10.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    build-essential \
    pkg-config \
    libcairo2-dev \
    ffmpeg \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    antiword \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
      | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
      > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    case "$arch" in \
      amd64) go_arch="amd64" ;; \
      arm64) go_arch="arm64" ;; \
      *) echo "Unsupported architecture for Go: $arch" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${go_arch}.tar.gz" -o /tmp/go.tgz; \
    rm -rf /usr/local/go; \
    tar -C /usr/local -xzf /tmp/go.tgz; \
    ln -sf /usr/local/go/bin/go /usr/local/bin/go; \
    ln -sf /usr/local/go/bin/gofmt /usr/local/bin/gofmt; \
    rm -f /tmp/go.tgz; \
    node --version; \
    go version

ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH="${DOTNET_ROOT}:${PATH}"
RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh && \
    bash /tmp/dotnet-install.sh --channel "${DOTNET_CHANNEL}" --quality ga --install-dir "${DOTNET_ROOT}" && \
    ln -sf "${DOTNET_ROOT}/dotnet" /usr/local/bin/dotnet && \
    rm -f /tmp/dotnet-install.sh && \
    dotnet --version

RUN pip install --no-cache-dir uv

WORKDIR /app

# ============================================
# Этап 2: сборщик - установка ВСЕХ зависимостей
# ============================================
FROM base-with-core AS builder-all
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-default-groups \
        --group core \
        --group agents \
        --group worker-base \
        --group rag-worker \
        --group crm \
        --group rag \
        --group sync \
        --group browser \
        --no-annotate --no-header --no-emit-project \
        -o /tmp/requirements.txt && \
    uv pip install --system -r /tmp/requirements.txt

# ============================================
# Этап 3: сборщик документации (статический сайт Zensical)
# ============================================
FROM python:3.13-slim AS docs-builder
RUN pip install --no-cache-dir "zensical>=0.0.32"
WORKDIR /app
COPY zensical.ru.toml zensical.en.toml ./
COPY docs ./docs
COPY scripts/docs_prepare.py scripts/extract_openapi.py scripts/openapi_to_markdown.py ./scripts/
RUN python scripts/docs_prepare.py && \
    zensical build --clean --config-file zensical.ru.toml && \
    zensical build --clean --config-file zensical.en.toml && \
    mkdir -p documentation-dist/en && \
    cp -a build/zensical-en-out/. documentation-dist/en/

# ============================================
# Этап 4: base-final - общий образ со всем кодом
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
FROM node:24-bookworm-slim AS js-vendor
WORKDIR /vendor
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ============================================
# Финальные стадии - отличаются только CMD/EXPOSE
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

# Capability Gateway
FROM base-final AS capability-gateway
EXPOSE 8016
CMD ["python", "-m", "apps.capability_gateway.main"]

# Python Code Runner
FROM base-final AS code-runner-python
EXPOSE 8017
CMD ["python", "-m", "apps.code_runner_python.main"]

# Node Code Runner
FROM base-final AS code-runner-node
EXPOSE 8018
CMD ["python", "-m", "apps.code_runner_node.main"]

# Go Code Runner
FROM base-final AS code-runner-go
EXPOSE 8019
CMD ["python", "-m", "apps.code_runner_go.main"]

# C# Code Runner
FROM base-final AS code-runner-csharp
EXPOSE 8020
CMD ["python", "-m", "apps.code_runner_csharp.main"]

# Migrations (init container)
FROM base-final AS migrations
CMD ["python", "-m", "scripts.db_migrate", "upgrade"]

# Full (для локальной разработки и тестов)
FROM base-final AS full
COPY --from=docs-builder /app/documentation-dist ./documentation-dist
COPY --from=js-vendor /vendor/node_modules/three/build /app/node_modules/three/build
COPY --from=js-vendor /vendor/node_modules/3d-force-graph/dist /app/node_modules/3d-force-graph/dist
EXPOSE 8001 8002 8003 8004 8005 8016 8017 8018 8019 8020
CMD ["python", "run_prod.py"]
