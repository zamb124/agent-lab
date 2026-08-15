"""Процесс language server на isolated vfs: stdio JSON-RPC ↔ WebSocket text frames."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import final

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from core.capabilities.lsp_stdio import BRIDGE_PID_FILENAME, BRIDGE_PORT_FILENAME
from core.capabilities.models import CapabilityLanguage, CodeLspSession, LspWorkspace
from core.capabilities.runtime_executables import (
    platform_runtime_bin_dir,
    resolve_runtime_executable,
)
from core.logging import get_logger

logger = get_logger(__name__)

LspCommandFactory = Callable[[], list[str]]
WorkspacePrepare = Callable[[Path, LspWorkspace], None]

_MAX_SESSIONS = 32
_BRIDGE_WAIT_SECONDS = 30.0
_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class _LiveSession:
    session_id: str
    language: CapabilityLanguage
    language_id: str
    root: Path
    document_path: str
    bridge: asyncio.subprocess.Process


@final
class LspSessionManager:
    """Один manager на code-runner: temp vfs + LS bridge-процесс + WS proxy."""

    def __init__(
        self,
        *,
        command_factory: LspCommandFactory,
        extra_prepare: WorkspacePrepare | None = None,
        extra_env: dict[str, str] | None = None,
        public_ws_prefix: str,
    ) -> None:
        self._command_factory = command_factory
        self._extra_prepare = extra_prepare
        self._extra_env = extra_env
        self._public_ws_prefix = public_ws_prefix.rstrip("/")
        self._sessions: dict[str, _LiveSession] = {}
        self._lock = asyncio.Lock()

    async def create(self, workspace: LspWorkspace) -> CodeLspSession:
        async with self._lock:
            await self._evict_if_needed()
            session_id = str(uuid.uuid4())
            root = Path(f"/tmp/platform-code-lsp-{session_id}")
            if root.exists():
                shutil.rmtree(root)
            root.mkdir(parents=True, exist_ok=True)
            for item in workspace.files:
                path = root / item.path
                path.parent.mkdir(parents=True, exist_ok=True)
                _ = path.write_text(item.content, encoding="utf-8")
            if self._extra_prepare is not None:
                self._extra_prepare(root, workspace)
            command = self._command_factory()
            solution = root / "UserCode.sln"
            if solution.is_file():
                command = [*command, "--solution", str(solution)]
            env = _bridge_process_env()
            if self._extra_env is not None:
                env.update(self._extra_env)
            env["CODE_LSP_SESSION_ID"] = session_id
            env["CODE_LSP_ROOT"] = str(root)
            env["CODE_LSP_COMMAND"] = json.dumps(command)
            bridge = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "core.capabilities.lsp_bridge",
                cwd=str(_REPO_ROOT),
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=None,
            )
            await _wait_bridge_port(root, bridge)
            live = _LiveSession(
                session_id=session_id,
                language=workspace.language,
                language_id=workspace.language_id,
                root=root,
                document_path=workspace.document_path,
                bridge=bridge,
            )
            self._sessions[session_id] = live
            logger.info(
                "code_lsp.session_started",
                session_id=session_id,
                language=workspace.language,
            )
            return self._to_model(live)

    async def close(self, session_id: str) -> None:
        async with self._lock:
            live = self._sessions.pop(session_id, None)
        if live is not None:
            await self._destroy(live)
            return
        await _destroy_session_root(Path(f"/tmp/platform-code-lsp-{session_id}"))

    async def aclose(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for live in sessions:
            await self._destroy(live)

    def exists(self, session_id: str) -> bool:
        return _read_bridge_port(Path(f"/tmp/platform-code-lsp-{session_id}")) is not None

    async def attach_websocket(self, websocket: WebSocket, session_id: str) -> None:
        port = _read_bridge_port(Path(f"/tmp/platform-code-lsp-{session_id}"))
        await websocket.accept()
        if port is None:
            await websocket.close(code=1008)
            return
        try:
            upstream = await websockets.connect(
                f"ws://127.0.0.1:{port}",
                open_timeout=10,
                ping_interval=None,
                max_size=None,
            )
        except Exception as exc:
            logger.exception("code_lsp.bridge_connect_failed", session_id=session_id)
            await websocket.close(code=1011)
            raise RuntimeError("language server bridge websocket failed") from exc

        async def client_to_bridge() -> None:
            while True:
                payload = await websocket.receive_text()
                await upstream.send(payload)

        async def bridge_to_client() -> None:
            while True:
                message = await upstream.recv()
                if isinstance(message, bytes):
                    await websocket.send_text(message.decode("utf-8"))
                else:
                    await websocket.send_text(message)

        try:
            _ = await asyncio.gather(client_to_bridge(), bridge_to_client())
        except WebSocketDisconnect:
            logger.info("code_lsp.ws_disconnected", session_id=session_id)
        except websockets.ConnectionClosed:
            logger.info("code_lsp.bridge_closed", session_id=session_id)
        except Exception as exc:
            logger.exception("code_lsp.ws_failed", session_id=session_id)
            await websocket.close(code=1011)
            raise RuntimeError("language server websocket failed") from exc
        finally:
            await upstream.close()
            await self.close(session_id)

    def _to_model(self, live: _LiveSession) -> CodeLspSession:
        document = live.root / live.document_path
        return CodeLspSession(
            session_id=live.session_id,
            language=live.language,
            language_id=live.language_id,
            root_uri=live.root.as_uri(),
            document_uri=document.as_uri(),
            ws_path=f"{self._public_ws_prefix}/{live.session_id}",
        )

    async def _evict_if_needed(self) -> None:
        roots = sorted(
            Path("/tmp").glob("platform-code-lsp-*"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        )
        overflow = len(roots) - _MAX_SESSIONS + 1
        if overflow <= 0:
            return
        for root in roots[:overflow]:
            session_id = root.name.removeprefix("platform-code-lsp-")
            live = self._sessions.pop(session_id, None)
            if live is not None:
                await self._destroy(live)
            else:
                await _destroy_session_root(root)

    async def _destroy(self, live: _LiveSession) -> None:
        if live.bridge.returncode is None:
            live.bridge.terminate()
            try:
                _ = await asyncio.wait_for(live.bridge.wait(), timeout=5)
            except TimeoutError:
                live.bridge.kill()
                _ = await live.bridge.wait()
        await _destroy_session_root(live.root)
        logger.info("code_lsp.session_closed", session_id=live.session_id)


def _bridge_process_env() -> dict[str, str]:
    env = os.environ.copy()
    runtime_bin = str(platform_runtime_bin_dir())
    env["PATH"] = f"{runtime_bin}{os.pathsep}{env.get('PATH', '')}"
    pythonpath = env.get("PYTHONPATH", "")
    repo = str(_REPO_ROOT)
    env["PYTHONPATH"] = repo if pythonpath == "" else f"{repo}{os.pathsep}{pythonpath}"
    env["PYTHONNOUSERSITE"] = "1"
    dotnet = resolve_runtime_executable("dotnet", override_env="CODE_RUNNER_DOTNET_BIN")
    if dotnet is not None:
        env["DOTNET_ROOT"] = str(Path(dotnet).resolve().parent)
    return env


def _read_bridge_port(root: Path) -> int | None:
    port_file = root / BRIDGE_PORT_FILENAME
    if not port_file.is_file():
        return None
    raw = port_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _read_bridge_pid(root: Path) -> int | None:
    pid_file = root / BRIDGE_PID_FILENAME
    if not pid_file.is_file():
        return None
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None
    return int(raw)


async def _kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = asyncio.get_running_loop().time() + 5
    while asyncio.get_running_loop().time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


async def _destroy_session_root(root: Path) -> None:
    pid = _read_bridge_pid(root)
    if pid is not None:
        await _kill_pid(pid)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


async def _wait_bridge_port(root: Path, bridge: asyncio.subprocess.Process) -> None:
    deadline = asyncio.get_running_loop().time() + _BRIDGE_WAIT_SECONDS
    while asyncio.get_running_loop().time() < deadline:
        if bridge.returncode is not None:
            raise RuntimeError(f"language server bridge exited {bridge.returncode}")
        if _read_bridge_port(root) is not None:
            return
        await asyncio.sleep(0.05)
    raise RuntimeError("language server bridge did not publish a port")
