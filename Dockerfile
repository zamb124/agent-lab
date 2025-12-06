# Минимальный базовый образ с core зависимостями
FROM python:3.12-slim AS base-core

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    make \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./

# Устанавливаем только core зависимости (без групп rag, docs)
RUN uv pip install --system -e .


# RAG образ с ML зависимостями (для worker)
FROM base-core AS base-rag

# Системные зависимости для PDF парсинга и OCR
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Сначала ставим CPU-only PyTorch (без CUDA, экономит ~2-3 GB)
RUN uv pip install --system \
    torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# Затем остальные RAG зависимости (torch уже установлен, не будет переустанавливаться)
RUN uv pip install --system --group rag


# Docs образ - минимальный, только для сборки документации
FROM python:3.12-slim AS base-docs

RUN pip install uv

WORKDIR /app

# Устанавливаем только mkdocs и его зависимости напрямую (без pyproject.toml)
RUN uv pip install --system \
    "mkdocs>=1.6.1" \
    "mkdocs-material>=9.6.21" \
    "mkdocs-static-i18n>=1.3.0" \
    "pymdown-extensions>=10.16.1"


# Сборка документации
FROM base-docs AS docs-builder

COPY mkdocs.yml ./
COPY docs/ ./docs/
COPY core/ ./core/
COPY apps/ ./apps/

RUN mkdocs build --clean


# Agents Service (легкий образ без ML)
FROM base-core AS agents

COPY core/ ./core/
COPY apps/agents/ ./apps/agents/
COPY apps/__init__.py ./apps/
COPY run_prod.py ./
COPY run_worker.py ./

EXPOSE 8001

CMD ["python", "run_prod.py"]


# Frontend Service (легкий образ без ML)
FROM base-core AS frontend

COPY core/ ./core/
COPY apps/ ./apps/
COPY run_frontend_prod.py ./

COPY --from=docs-builder /app/site ./site

EXPOSE 8002

CMD ["python", "run_frontend_prod.py"]


# CRM Service (легкий образ без ML)
FROM base-core AS crm

COPY core/ ./core/
COPY apps/crm/ ./apps/crm/
COPY apps/__init__.py ./apps/
COPY run_crm_prod.py ./

EXPOSE 8003

CMD ["python", "run_crm_prod.py"]


# Worker (с RAG/ML зависимостями)
FROM base-rag AS worker

COPY core/ ./core/
COPY apps/ ./apps/
COPY run_worker.py ./

CMD ["python", "run_worker.py"]


# Full (для локальной разработки - с ML)
FROM base-rag AS full

COPY core/ ./core/
COPY apps/ ./apps/
COPY run_prod.py ./
COPY run_frontend_prod.py ./
COPY run_worker.py ./
COPY run.py ./

COPY --from=docs-builder /app/site ./site

EXPOSE 8001 8002

CMD ["python", "run_prod.py"]
