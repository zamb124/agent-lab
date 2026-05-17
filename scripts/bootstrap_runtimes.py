#!/usr/bin/env python3
"""Install language runtimes required by local sandbox runners."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

RUNTIME_ROOT = Path(
    os.environ.get("PLATFORM_RUNTIME_DIR", "~/.cache/agent-lab/runtimes")
).expanduser()
BIN_DIR = RUNTIME_ROOT / "bin"
DOTNET_CHANNEL = os.environ.get("DOTNET_CHANNEL", "10.0")
GO_VERSION = os.environ.get("GO_VERSION", "1.26.1")
NODE_MAJOR = int(os.environ.get("NODE_MAJOR", "24"))


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"runtime-bootstrap: {' '.join(command)}", flush=True)
    subprocess.run(command, check=True, env=env)


def _download(url: str, destination: Path) -> None:
    print(f"runtime-bootstrap: download {url}", flush=True)
    with urllib.request.urlopen(url, timeout=180) as response:
        destination.write_bytes(response.read())


def _runtime_os() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "darwin"
    if system == "linux":
        return "linux"
    raise RuntimeError(f"Unsupported OS for managed runtimes: {system}")


def _runtime_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise RuntimeError(f"Unsupported architecture for managed runtimes: {machine}")


def _node_arch() -> str:
    arch = _runtime_arch()
    return "x64" if arch == "amd64" else "arm64"


def _ensure_dirs() -> None:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)


def _symlink(source: Path, name: str) -> None:
    target = BIN_DIR / name
    target.unlink(missing_ok=True)
    target.symlink_to(source)


def _command_output(command: list[str]) -> str | None:
    executable = shutil.which(command[0])
    if executable is None:
        return None
    completed = subprocess.run(
        [executable, *command[1:]],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _node_ready() -> bool:
    output = _command_output(["node", "--version"])
    if output is None:
        return False
    match = re.fullmatch(r"v(\d+)\..+", output)
    return bool(match and int(match.group(1)) >= NODE_MAJOR)


def _go_ready() -> bool:
    output = _command_output(["go", "version"])
    if output is None:
        return False
    return f"go{GO_VERSION}" in output


def _dotnet_ready() -> bool:
    output = _command_output(["dotnet", "--list-sdks"])
    if output is None:
        return False
    return any(line.startswith(f"{DOTNET_CHANNEL}.") for line in output.splitlines())


def _install_node() -> None:
    node_os = _runtime_os()
    node_arch = _node_arch()
    platform_id = f"{node_os}-{node_arch}"
    latest_root = f"https://nodejs.org/dist/latest-v{NODE_MAJOR}.x"
    with urllib.request.urlopen(f"{latest_root}/SHASUMS256.txt", timeout=180) as response:
        shasums = response.read().decode("utf-8")
    archive_name = ""
    for line in shasums.splitlines():
        candidate = line.split()[-1]
        if candidate.endswith(f"-{platform_id}.tar.xz"):
            archive_name = candidate
            break
    if not archive_name:
        raise RuntimeError(f"Node.js v{NODE_MAJOR} archive not found for {platform_id}")

    install_dir = RUNTIME_ROOT / f"node-v{NODE_MAJOR}"
    with tempfile.TemporaryDirectory(prefix="node-install-", dir=RUNTIME_ROOT) as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / archive_name
        _download(f"{latest_root}/{archive_name}", archive_path)
        with tarfile.open(archive_path, "r:xz") as archive:
            archive.extractall(tmp_path, filter="data")
        extracted = tmp_path / archive_name.removesuffix(".tar.xz")
        if install_dir.exists():
            shutil.rmtree(install_dir)
        shutil.move(str(extracted), install_dir)
    _symlink(install_dir / "bin" / "node", "node")
    _symlink(install_dir / "bin" / "npm", "npm")
    _symlink(install_dir / "bin" / "npx", "npx")


def _install_go() -> None:
    go_os = _runtime_os()
    go_arch = _runtime_arch()
    archive_name = f"go{GO_VERSION}.{go_os}-{go_arch}.tar.gz"
    install_dir = RUNTIME_ROOT / f"go-{GO_VERSION}"
    with tempfile.TemporaryDirectory(prefix="go-install-", dir=RUNTIME_ROOT) as tmp:
        tmp_path = Path(tmp)
        archive_path = tmp_path / archive_name
        _download(f"https://go.dev/dl/{archive_name}", archive_path)
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(tmp_path, filter="data")
        extracted = tmp_path / "go"
        if install_dir.exists():
            shutil.rmtree(install_dir)
        shutil.move(str(extracted), install_dir)
    _symlink(install_dir / "bin" / "go", "go")
    _symlink(install_dir / "bin" / "gofmt", "gofmt")


def _install_dotnet() -> None:
    install_dir = RUNTIME_ROOT / f"dotnet-{DOTNET_CHANNEL}"
    install_dir.mkdir(parents=True, exist_ok=True)
    script_path = RUNTIME_ROOT / "dotnet-install.sh"
    _download("https://dot.net/v1/dotnet-install.sh", script_path)
    _run(
        [
            "bash",
            str(script_path),
            "--channel",
            DOTNET_CHANNEL,
            "--quality",
            "ga",
            "--install-dir",
            str(install_dir),
        ]
    )
    _symlink(install_dir / "dotnet", "dotnet")


def _print_versions() -> None:
    env = dict(os.environ)
    env["PATH"] = f"{BIN_DIR}:{env.get('PATH', '')}"
    for command in (["node", "--version"], ["go", "version"], ["dotnet", "--list-sdks"]):
        completed = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
        print(completed.stdout.strip(), flush=True)


def main() -> None:
    _ensure_dirs()
    if _node_ready():
        print("runtime-bootstrap: node is ready", flush=True)
    else:
        _install_node()
    if _go_ready():
        print("runtime-bootstrap: go is ready", flush=True)
    else:
        _install_go()
    if _dotnet_ready():
        print("runtime-bootstrap: dotnet is ready", flush=True)
    else:
        _install_dotnet()
    _print_versions()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"runtime-bootstrap failed: {exc}", file=sys.stderr, flush=True)
        raise
