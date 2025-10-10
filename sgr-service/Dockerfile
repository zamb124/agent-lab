FROM python:3.12-slim

WORKDIR /app

# Устанавливаем системные зависимости и git
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:/root/.local/bin:$PATH"

# Клонируем SGR Deep Research из GitHub
RUN git clone https://github.com/vamplabAI/sgr-deep-research.git /tmp/sgr && \
    mv /tmp/sgr/* /app/ && \
    rm -rf /tmp/sgr

# Копируем entrypoint для генерации конфига
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Устанавливаем зависимости через uv
RUN uv pip install --system -e .

# Создаем директории для отчетов и логов
RUN mkdir -p reports logs

# Порт сервиса
EXPOSE 8010

# Используем entrypoint для генерации config.yaml
ENTRYPOINT ["/app/entrypoint.sh"]

