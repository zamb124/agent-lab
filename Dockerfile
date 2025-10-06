FROM python:3.12-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем uv для быстрой установки пакетов
RUN pip install uv

# Создаем рабочую директорию
WORKDIR /app

# Копируем файлы проекта (context = .)
COPY pyproject.toml ./
COPY app/ ./app/
COPY run.py ./
COPY run_worker.py ./
COPY conf.json ./

# Устанавливаем зависимости
RUN uv pip install --system -e .

# Открываем порт
EXPOSE 8001

# Команда запуска
CMD ["python", "run.py"]
