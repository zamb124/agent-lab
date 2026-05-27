FROM ghcr.io/astral-sh/uv:trixie-slim

WORKDIR /app

ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV UV_PYTHON_PREFERENCE=only-managed
ENV PYTHON_GIL=0
RUN uv python install 3.14t && uv python pin 3.14t

COPY pyproject.toml uv.lock ./
COPY apps/test_a2a_service ./apps/test_a2a_service
COPY apps/agents/src ./apps/agents/src
COPY apps/agents/__init__.py ./apps/agents/
COPY core ./core

RUN uv sync --frozen

EXPOSE 8003

CMD ["uv", "run", "granian", "--interface", "asgi", "apps.test_a2a_service.main:app", "--host", "0.0.0.0", "--port", "8003", "--http", "auto"]

