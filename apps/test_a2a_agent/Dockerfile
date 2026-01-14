FROM python:3.13-slim

WORKDIR /app

# Копируем только необходимые файлы для тестового агента
COPY apps/test_a2a_agent ./apps/test_a2a_agent
COPY apps/__init__.py ./apps/

# Устанавливаем только необходимые зависимости
# Минимальный набор для A2A агента без платформы
RUN pip install --no-cache-dir \
    uvicorn>=0.27.0 \
    httpx>=0.27.0 \
    a2a-sdk>=0.3.7 \
    starlette>=0.36.0 \
    sse-starlette>=2.0.0

# Порт сервиса
EXPOSE 8005

# Запуск сервиса
CMD ["python", "-m", "uvicorn", "apps.test_a2a_agent.main:app", "--host", "0.0.0.0", "--port", "8005"]

