FROM ghcr.io/astral-sh/uv:bookworm-slim

WORKDIR /app

ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV UV_PYTHON_PREFERENCE=only-managed
ENV PYTHON_GIL=0
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
RUN uv python install 3.14t && uv venv --python 3.14t "${VIRTUAL_ENV}"

RUN uv pip install --python "${VIRTUAL_ENV}/bin/python" fastapi granian>=2.7.4 pydantic

COPY main.py .

EXPOSE 8080

CMD ["python", "main.py"]

