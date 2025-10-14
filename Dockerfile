FROM python:3.12-slim AS base

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    make \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем uv для быстрой установки пакетов
RUN pip install uv

# Создаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml ./
COPY README.md ./

# Устанавливаем зависимости
RUN uv pip install --system -e .

# Этап сборки документации
FROM base AS docs-builder

# Копируем файлы для документации
COPY mkdocs.yml ./
COPY docs/ ./docs/
COPY app/ ./app/

# Собираем документацию
RUN uv run mkdocs build --clean

# Финальный образ приложения
FROM base AS app

# Копируем код приложения
COPY app/ ./app/
COPY run.py ./
COPY run_worker.py ./
COPY conf.json ./

# Копируем собранную документацию из docs-builder
COPY --from=docs-builder /app/site ./site

# Открываем порт
EXPOSE 8001

# Команда запуска
CMD ["python", "run.py"]
