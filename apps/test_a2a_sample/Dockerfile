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
    granian>=2.8.6 \
    "httpx2[http2]>=2.16.0" \
    "a2a-sdk[fastapi]>=1.0,<2"

EXPOSE 8005

CMD ["granian", "--interface", "asgi", "apps.test_a2a_sample.main:app", "--host", "0.0.0.0", "--port", "8005", "--http", "auto"]

