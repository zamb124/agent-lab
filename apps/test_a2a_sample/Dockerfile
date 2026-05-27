FROM ghcr.io/astral-sh/uv:bookworm-slim

WORKDIR /app

ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV UV_PYTHON_PREFERENCE=only-managed
ENV PYTHON_GIL=0
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN uv python install 3.14t && uv venv --python 3.14t "${VIRTUAL_ENV}"

COPY apps/test_a2a_sample ./apps/test_a2a_sample
COPY apps/__init__.py ./apps/

RUN uv pip install --python "${VIRTUAL_ENV}/bin/python" \
    granian>=2.7.4 \
    httpx>=0.27.0 \
    a2a-sdk>=0.3.7 \
    starlette>=0.36.0 \
    sse-starlette>=2.0.0

EXPOSE 8005

CMD ["granian", "--interface", "asgi", "apps.test_a2a_sample.main:app", "--host", "0.0.0.0", "--port", "8005", "--http", "auto"]

