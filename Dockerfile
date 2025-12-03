FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    make \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./

# CPU-only PyTorch (без CUDA, экономит ~2-3 GB)
ENV PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN uv pip install --system -e .


# Сборка документации
FROM base AS docs-builder

COPY mkdocs.yml ./
COPY docs/ ./docs/
COPY core/ ./core/
COPY apps/ ./apps/

RUN uv run mkdocs build --clean


# Agents Service
FROM base AS agents

COPY core/ ./core/
COPY apps/agents/ ./apps/agents/
COPY apps/__init__.py ./apps/
COPY run_prod.py ./
COPY run_worker.py ./
COPY conf.json ./

EXPOSE 8001

CMD ["python", "run_prod.py"]


# Frontend Service
FROM base AS frontend

COPY core/ ./core/
COPY apps/ ./apps/
COPY run_frontend_prod.py ./
COPY conf.json ./

COPY --from=docs-builder /app/site ./site

EXPOSE 8002

CMD ["python", "run_frontend_prod.py"]


# Worker (требует доступ ко всем apps для импорта задач)
FROM base AS worker

COPY core/ ./core/
COPY apps/ ./apps/
COPY run_worker.py ./
COPY conf.json ./

CMD ["python", "run_worker.py"]


# Full (для локальной разработки)
FROM base AS full

COPY core/ ./core/
COPY apps/ ./apps/
COPY run_prod.py ./
COPY run_frontend_prod.py ./
COPY run_worker.py ./
COPY run.py ./
COPY conf.json ./

COPY --from=docs-builder /app/site ./site

EXPOSE 8001 8002

CMD ["python", "run_prod.py"]
