from __future__ import annotations

from apps.guest_runtime.services.slots import docker_file
from core.guest_runtime.models import GuestLanguage


def test_docker_file_python_uv_lock_uses_frozen_sync_and_venv_path() -> None:
    dockerfile = docker_file(
        GuestLanguage.PYTHON,
        {
            "pyproject.toml": b"[project]\nname = 'demo'\n",
            "uv.lock": b"version = 1\n",
            "main.py": b"print(1)\n",
        },
    )
    assert "COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/" in dockerfile
    assert "ENV UV_PYTHON_DOWNLOADS=0" in dockerfile
    assert "RUN uv sync --frozen --no-dev --no-cache" in dockerfile
    assert 'ENV PATH="/src/.venv/bin:$PATH"' in dockerfile
    assert "pip install" not in dockerfile


def test_docker_file_python_pyproject_without_lock() -> None:
    dockerfile = docker_file(
        GuestLanguage.PYTHON,
        {"pyproject.toml": b"[project]\nname = 'demo'\n", "main.py": b"print(1)\n"},
    )
    assert "RUN uv sync --no-dev --no-cache" in dockerfile
    assert "--frozen" not in dockerfile
    assert 'ENV PATH="/src/.venv/bin:$PATH"' in dockerfile


def test_docker_file_python_requirements() -> None:
    dockerfile = docker_file(
        GuestLanguage.PYTHON,
        {"requirements.txt": b"requests==2.32.0\n", "main.py": b"print(1)\n"},
    )
    assert "RUN pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "uv sync" not in dockerfile


def test_docker_file_python_stdlib_has_no_install() -> None:
    dockerfile = docker_file(GuestLanguage.PYTHON, {"main.py": b"print(1)\n"})
    assert "uv sync" not in dockerfile
    assert "pip install" not in dockerfile
    assert "ENTRYPOINT" in dockerfile


def test_docker_file_node_lock_uses_npm_ci() -> None:
    dockerfile = docker_file(
        GuestLanguage.NODE,
        {
            "package.json": b'{"name":"demo"}\n',
            "package-lock.json": b'{"lockfileVersion": 3}\n',
            "main.js": b"console.log(1)\n",
        },
    )
    assert "RUN npm ci --omit=dev" in dockerfile
    assert "npm install" not in dockerfile


def test_docker_file_node_package_json_only() -> None:
    dockerfile = docker_file(
        GuestLanguage.NODE,
        {"package.json": b'{"name":"demo"}\n', "main.js": b"console.log(1)\n"},
    )
    assert "RUN npm install --omit=dev" in dockerfile
    assert "npm ci" not in dockerfile
