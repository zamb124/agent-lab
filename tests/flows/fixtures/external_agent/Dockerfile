FROM ghcr.io/astral-sh/uv:trixie-slim

WORKDIR /app

ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
ENV UV_PYTHON_PREFERENCE=only-managed
ENV PYTHON_GIL=0
RUN uv python install 3.14t && uv python pin 3.14t

RUN uv pip install --system fastapi granian>=2.7.4 pydantic

COPY main.py .

EXPOSE 8080

CMD ["python", "main.py"]

