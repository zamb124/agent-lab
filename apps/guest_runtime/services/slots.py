"""Исполнители фермы: inprocess / docker без auto-fallback."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import assert_never
from urllib.parse import urlparse

import httpx2

from core.config.models import GuestRuntimeFarmConfig
from core.guest_runtime.models import GuestExecutorKind, GuestLanguage, GuestLease
from core.logging import get_logger
from core.utils.tcp_port import listening_tcp_port

logger = get_logger(__name__)

SHIM_SOURCE = Path(__file__).resolve().parents[1] / "shim" / "pid1.py"
GUEST_DOCKER_NETWORK = "guest-runtime"


@dataclass(slots=True)
class GuestSlot:
    executor: GuestExecutorKind
    shim_url: str
    process_id: int | None
    container_id: str | None
    process: asyncio.subprocess.Process | None = None
    log_follow: asyncio.subprocess.Process | None = None
    drain_task: asyncio.Task[None] | None = field(default=None, repr=False)
    log_task_id: str | None = None
    log_session_id: str | None = None
    log_context_id: str | None = None
    log_request_id: str | None = None
    log_trace_id: str | None = None


def compute_source_digest(contents: dict[str, bytes]) -> str:
    hasher = hashlib.sha256()
    for relative_path in sorted(contents):
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(contents[relative_path]).digest())
    return hasher.hexdigest()


def docker_image_tag(source_digest_hex: str) -> str:
    if len(source_digest_hex) < 16:
        raise ValueError("source digest hex is too short for docker tag")
    return f"guest-runtime:{source_digest_hex[:16]}"


def docker_cpus(guest_cpu: str) -> str:
    raw = guest_cpu.strip()
    if raw == "":
        raise ValueError("guest_cpu is required")
    if raw.endswith("m"):
        milli_raw = raw[:-1]
        if not milli_raw.isdigit():
            raise ValueError(f"invalid guest_cpu millicores: {guest_cpu}")
        milli = int(milli_raw)
        if milli < 1:
            raise ValueError("guest_cpu millicores must be >= 1")
        return str(milli / 1000.0)
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise ValueError(f"invalid guest_cpu: {guest_cpu}") from exc
    if parsed <= 0:
        raise ValueError("guest_cpu must be > 0")
    return raw


def docker_memory(guest_memory: str) -> str:
    raw = guest_memory.strip()
    if raw == "":
        raise ValueError("guest_memory is required")
    lowered = raw.lower()
    binary_to_docker = (("gi", "g"), ("mi", "m"), ("ki", "k"))
    for suffix, docker_unit in binary_to_docker:
        if lowered.endswith(suffix):
            quantity = raw[: -len(suffix)]
            if not quantity.isdigit():
                raise ValueError(f"invalid guest_memory: {guest_memory}")
            if int(quantity) < 1:
                raise ValueError("guest_memory quantity must be >= 1")
            return f"{quantity}{docker_unit}"
    if lowered.endswith(("g", "m", "k", "b")):
        quantity = raw[:-1]
        if not quantity.isdigit():
            raise ValueError(f"invalid guest_memory: {guest_memory}")
        if int(quantity) < 1:
            raise ValueError("guest_memory quantity must be >= 1")
        return f"{quantity}{lowered[-1]}"
    if raw.isdigit():
        if int(raw) < 1:
            raise ValueError("guest_memory bytes must be >= 1")
        return raw
    raise ValueError(f"invalid guest_memory: {guest_memory}")


def _bind_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return listening_tcp_port(sock, label="socket bind")


async def _wait_health(url: str, *, attempts: int = 50) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            async with httpx2.AsyncClient(timeout=1.0) as client:
                response = await client.get(f"{url}/health")
                if response.status_code == 200:
                    return
        except Exception as exc:
            last_error = exc
        await asyncio.sleep(0.1)
    detail = str(last_error) if last_error is not None else "no response"
    raise RuntimeError(f"guest shim health failed: {detail}")


async def _run_docker(*args: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "docker",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = out.decode("utf-8", errors="replace")
    if proc.returncode is None:
        raise RuntimeError("docker process has no return code")
    return proc.returncode, text


async def require_docker() -> None:
    if shutil.which("docker") is None:
        raise RuntimeError("docker executor requires docker CLI")
    code, output = await _run_docker("info")
    if code != 0:
        raise RuntimeError(f"docker executor: docker daemon is not available: {output}")


async def ensure_docker_network() -> None:
    await require_docker()
    inspect_code, _ = await _run_docker("network", "inspect", GUEST_DOCKER_NETWORK)
    if inspect_code == 0:
        return
    create_code, create_out = await _run_docker("network", "create", GUEST_DOCKER_NETWORK)
    if create_code != 0:
        raise RuntimeError(f"docker network create failed: {create_out}")


def materialize_source_tree(root: Path, contents: dict[str, bytes]) -> None:
    if root.exists():
        shutil.rmtree(root)
    _ = root.mkdir(parents=True)
    for relative_path, payload in contents.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_bytes(payload)
    shim_target = root.parent / "pid1.py"
    _ = shim_target.write_bytes(SHIM_SOURCE.read_bytes())


def rewrite_loopback_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if hostname not in {"localhost", "127.0.0.1"}:
        return url
    port = parsed.port
    if port is None:
        raise ValueError(f"loopback guest URL requires an explicit port: {url}")
    netloc = f"host.docker.internal:{port}"
    if parsed.username is not None:
        raise ValueError("guest URL must not contain userinfo")
    return parsed._replace(netloc=netloc).geturl()


def extra_hosts_for_urls(urls: list[str]) -> list[tuple[str, str]]:
    hosts: list[tuple[str, str]] = []
    seen: set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname is None or hostname.strip() == "":
            raise ValueError(f"url has no hostname: {url}")
        if hostname in {"localhost", "127.0.0.1"}:
            continue
        if hostname in seen:
            continue
        seen.add(hostname)
        infos = socket.getaddrinfo(hostname, parsed.port or 80, type=socket.SOCK_STREAM)
        if not infos:
            raise RuntimeError(f"cannot resolve egress host {hostname}")
        sockaddr = infos[0][4]
        ip = sockaddr[0]
        if not isinstance(ip, str) or ip.strip() == "":
            raise RuntimeError(f"cannot resolve egress host {hostname}")
        hosts.append((hostname, ip))
    return hosts


def _root_file_names(contents: dict[str, bytes]) -> frozenset[str]:
    names: set[str] = set()
    for relative_path in contents:
        if "/" in relative_path:
            continue
        if relative_path.strip() == "":
            raise ValueError("code_agent source path must not be empty")
        names.add(relative_path)
    return frozenset(names)


def docker_file(language: GuestLanguage, contents: dict[str, bytes]) -> str:
    resolved = GuestLanguage(language)
    names = _root_file_names(contents)
    if resolved == GuestLanguage.PYTHON:
        lines = [
            "FROM python:3.14-slim",
            "COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/",
            "ENV UV_PYTHON_DOWNLOADS=0",
            "COPY pid1.py /guest/pid1.py",
            "COPY src /src",
            "WORKDIR /src",
        ]
        if "pyproject.toml" in names and "uv.lock" in names:
            lines.append("RUN uv sync --frozen --no-dev --no-cache")
            lines.append('ENV PATH="/src/.venv/bin:$PATH"')
        elif "pyproject.toml" in names:
            lines.append("RUN uv sync --no-dev --no-cache")
            lines.append('ENV PATH="/src/.venv/bin:$PATH"')
        elif "requirements.txt" in names:
            lines.append("RUN pip install --no-cache-dir -r requirements.txt")
        lines.append('ENTRYPOINT ["python3", "/guest/pid1.py"]')
        return "\n".join(lines) + "\n"
    if resolved == GuestLanguage.NODE:
        lines = [
            "FROM python:3.14-slim",
            "RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm "
            + "&& rm -rf /var/lib/apt/lists/*",
            "COPY pid1.py /guest/pid1.py",
            "COPY src /src",
            "WORKDIR /src",
        ]
        if "package.json" in names and "package-lock.json" in names:
            lines.append("RUN npm ci --omit=dev")
        elif "package.json" in names:
            lines.append("RUN npm install --omit=dev")
        lines.append('ENTRYPOINT ["python3", "/guest/pid1.py"]')
        return "\n".join(lines) + "\n"
    assert_never(resolved)


async def start_inprocess_slot(
    *,
    data_dir: Path,
    flow_id: str,
    node_id: str,
    contents: dict[str, bytes],
    env: dict[str, str],
) -> GuestSlot:
    slot_root = data_dir / flow_id / node_id
    src_root = slot_root / "src"
    materialize_source_tree(src_root, contents)
    port = _bind_free_port()
    shim_path = slot_root / "pid1.py"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(shim_path),
        "--port",
        str(port),
        cwd=str(src_root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    shim_url = f"http://127.0.0.1:{port}"
    await _wait_health(shim_url)
    logger.info("guest.slot.started", executor="inprocess", shim_url=shim_url, pid=process.pid)
    return GuestSlot(
        executor=GuestExecutorKind.INPROCESS,
        shim_url=shim_url,
        process_id=process.pid,
        container_id=None,
        process=process,
    )


async def docker_image_inspect(image_ref: str) -> tuple[str, int] | None:
    await require_docker()
    inspect_code, inspect_out = await _run_docker(
        "inspect",
        "--format",
        "{{.Id}} {{.Size}}",
        image_ref,
    )
    if inspect_code != 0:
        return None
    parts = inspect_out.strip().split()
    if len(parts) != 2:
        raise RuntimeError(f"docker inspect unexpected output: {inspect_out}")
    image_id = parts[0]
    if not image_id.startswith("sha256:"):
        raise RuntimeError(f"docker image id is not sha256: {image_id}")
    image_bytes = int(parts[1])
    if image_bytes < 0:
        raise RuntimeError("docker image size is negative")
    return image_id, image_bytes


async def build_docker_image(
    *,
    language: GuestLanguage,
    contents: dict[str, bytes],
    data_dir: Path,
    flow_id: str,
    node_id: str,
    source_digest_hex: str,
) -> tuple[str, int]:
    await require_docker()
    build_root = data_dir / "docker-build" / flow_id / node_id
    src_root = build_root / "src"
    materialize_source_tree(src_root, contents)
    dockerfile = docker_file(language, contents)
    _ = (build_root / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    tag = docker_image_tag(source_digest_hex)
    code, output = await _run_docker("build", "-t", tag, str(build_root))
    if code != 0:
        raise RuntimeError(f"docker build failed: {output}")
    inspected = await docker_image_inspect(tag)
    if inspected is None:
        raise RuntimeError(f"docker inspect failed after build: {tag}")
    return inspected


async def start_docker_slot(
    *,
    farm: GuestRuntimeFarmConfig,
    image_digest: str,
    env: dict[str, str],
    extra_host_pairs: list[tuple[str, str]],
) -> GuestSlot:
    await require_docker()
    await ensure_docker_network()
    inspect_code, _ = await _run_docker("image", "inspect", image_digest)
    if inspect_code != 0:
        raise RuntimeError(f"docker image is missing for digest {image_digest}")
    env_args: list[str] = []
    for key, value in env.items():
        env_args.extend(["-e", f"{key}={value}"])
    host_args: list[str] = ["--add-host", "host.docker.internal:host-gateway"]
    for hostname, ip in extra_host_pairs:
        host_args.extend(["--add-host", f"{hostname}:{ip}"])
    run_args = [
        "run",
        "-d",
        "--rm",
        "--network",
        GUEST_DOCKER_NETWORK,
        "--cpus",
        docker_cpus(farm.guest_cpu),
        "--memory",
        docker_memory(farm.guest_memory),
        "--pids-limit",
        str(farm.pids_limit),
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "-p",
        "127.0.0.1::8080",
        *host_args,
        *env_args,
        image_digest,
        "--port",
        "8080",
    ]
    code, output = await _run_docker(*run_args)
    if code != 0:
        raise RuntimeError(f"docker run failed: {output}")
    container_id = output.strip().split("\n", 1)[0]
    if container_id == "":
        raise RuntimeError("docker run returned empty container id")
    shim_url = await docker_shim_url(container_id)
    await _wait_health(shim_url)
    follow = await asyncio.create_subprocess_exec(
        "docker",
        "logs",
        "-f",
        container_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    return GuestSlot(
        executor=GuestExecutorKind.DOCKER,
        shim_url=shim_url,
        process_id=None,
        container_id=container_id,
        log_follow=follow,
    )


async def docker_shim_url(container_id: str) -> str:
    code, output = await _run_docker("port", container_id, "8080/tcp")
    if code != 0:
        raise RuntimeError(f"docker port failed: {output}")
    mapping = output.strip().split("\n", 1)[0]
    if mapping == "":
        raise RuntimeError(f"docker port mapping missing for {container_id}")
    host_port = mapping.rsplit(":", 1)[-1]
    return f"http://127.0.0.1:{host_port}"


async def restore_docker_slot(container_id: str) -> GuestSlot | None:
    await require_docker()
    code, output = await _run_docker(
        "inspect",
        "--format",
        "{{.State.Running}}",
        container_id,
    )
    if code != 0:
        return None
    if output.strip() != "true":
        return None
    shim_url = await docker_shim_url(container_id)
    await _wait_health(shim_url)
    follow = await asyncio.create_subprocess_exec(
        "docker",
        "logs",
        "-f",
        "--tail",
        "0",
        container_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    return GuestSlot(
        executor=GuestExecutorKind.DOCKER,
        shim_url=shim_url,
        process_id=None,
        container_id=container_id,
        log_follow=follow,
    )


def signal_process(process_id: int, sig: int) -> bool:
    """Доставить сигнал процессу. False — pid уже не существует."""
    try:
        os.kill(process_id, sig)
    except ProcessLookupError:
        return False
    return True


async def restore_inprocess_slot(lease: GuestLease) -> GuestSlot | None:
    if lease.process_id is None:
        return None
    if not signal_process(lease.process_id, 0):
        return None
    try:
        await _wait_health(lease.shim_url, attempts=5)
    except RuntimeError:
        return None
    return GuestSlot(
        executor=GuestExecutorKind.INPROCESS,
        shim_url=lease.shim_url,
        process_id=lease.process_id,
        container_id=None,
    )


async def maybe_delete_docker_image(image_digest: str, executor: GuestExecutorKind) -> None:
    if executor != GuestExecutorKind.DOCKER:
        return
    await require_docker()
    code, output = await _run_docker("rmi", "-f", image_digest)
    _ = code, output


async def stop_slot(slot: GuestSlot) -> None:
    if slot.drain_task is not None and not slot.drain_task.done():
        _ = slot.drain_task.cancel()
    if slot.log_follow is not None and slot.log_follow.returncode is None:
        slot.log_follow.terminate()
    if slot.executor == GuestExecutorKind.INPROCESS:
        if slot.process is not None and slot.process.returncode is None:
            slot.process.terminate()
            return
        if slot.process_id is None:
            raise RuntimeError("inprocess slot missing process_id")
        _ = signal_process(slot.process_id, 15)
        return
    if slot.executor == GuestExecutorKind.DOCKER:
        if slot.container_id is None:
            raise RuntimeError("docker slot missing container_id")
        code, output = await _run_docker("rm", "-f", slot.container_id)
        _ = code, output
        return
    raise RuntimeError(f"unknown executor: {slot.executor}")


