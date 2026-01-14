FROM python:3.13-slim

WORKDIR /app

# Копируем только необходимые файлы
COPY pyproject.toml uv.lock ./
COPY apps/test_a2a_service ./apps/test_a2a_service
COPY apps/agents/src ./apps/agents/src
COPY apps/agents/__init__.py ./apps/agents/
COPY core ./core

# Устанавливаем uv и зависимости
RUN pip install uv && \
    uv sync --frozen

# Порт сервиса
EXPOSE 8003

# Запуск сервиса
CMD ["uv", "run", "python", "-m", "uvicorn", "apps.test_a2a_service.main:app", "--host", "0.0.0.0", "--port", "8003"]

