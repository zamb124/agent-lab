FROM python:3.12-slim

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

# Копируем файлы проекта (context = .)
COPY pyproject.toml ./
COPY mkdocs.yml ./
COPY README.md ./
COPY docs/ ./docs/
COPY app/ ./app/
COPY run.py ./
COPY run_worker.py ./
COPY conf.json ./

# Устанавливаем зависимости
RUN uv pip install --system -e .

# Собираем документацию
RUN uv run mkdocs build --clean

# Открываем порт
EXPOSE 8001

# Команда запуска
CMD ["python", "run.py"]
