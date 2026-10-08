"""Отдельный процесс: language server stdio ↔ WebSocket на 127.0.0.1. Не привязан к granian worker."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from websockets.asyncio.server import Server, ServerConnection, serve

from core.capabilities.lsp_stdio import (
    BRIDGE_PID_FILENAME,
    BRIDGE_PORT_FILENAME,
    drain_lsp_stderr,
    encode_lsp_rpc_frame,
    read_lsp_rpc_frame,
)
from core.logging import get_logger
from core.types import parse_json_value, require_json_array
from core.utils.background import run_with_log_context
from core.utils.process_env import child_process_env
from core.utils.tcp_port import listening_tcp_port

logger = get_logger(__name__)

_IDLE_TIMEOUT_SECONDS = 300.0


def bridge_invocation(argv: list[str]) -> tuple[str, Path, list[str]]:
    """Аргументы процесса: session_id, корень vfs, JSON-список команды language server."""
    if len(argv) != 4:
        raise RuntimeError("lsp bridge expects session_id, root and command json")
    session_id = argv[1].strip()
    root_raw = argv[2].strip()
    if session_id == "" or root_raw == "":
        raise RuntimeError("lsp bridge session_id and root are required")
    raw_command = require_json_array(
        parse_json_value(argv[3], "lsp bridge command"),
        "lsp bridge command",
    )
    command: list[str] = []
    for item in raw_command:
        if not isinstance(item, str) or item.strip() == "":
            raise RuntimeError("lsp bridge command must be a JSON list of non-empty strings")
        command.append(item)
    if command == []:
        raise RuntimeError("lsp bridge command must not be empty")
    return session_id, Path(root_raw), command


async def _run_bridge(session_id: str, root: Path, command: list[str]) -> None:
    _ = (root / BRIDGE_PID_FILENAME).write_text(str(os.getpid()), encoding="utf-8")
    env = child_process_env()
    _ = env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(root),
        env=env,
    )
    if process.stdin is None or process.stdout is None:
        process.kill()
        raise RuntimeError("language server stdio is required")
    stdin = process.stdin
    stdout = process.stdout
    idle_handle: asyncio.TimerHandle | None = None
    server_holder: list[Server] = []

    def _arm_idle() -> None:
        nonlocal idle_handle
        loop = asyncio.get_running_loop()
        if idle_handle is not None:
            idle_handle.cancel()
        idle_handle = loop.call_later(_IDLE_TIMEOUT_SECONDS, _request_shutdown)

    def _request_shutdown() -> None:
        if server_holder:
            server_holder[0].close()

    _ = run_with_log_context(
        drain_lsp_stderr(process, session_id),
        name=f"code_lsp.bridge_stderr.{session_id}",
        background_kind="code_lsp",
    )

    async def handler(connection: ServerConnection) -> None:
        _arm_idle()

        async def client_to_server() -> None:
            async for payload in connection:
                _arm_idle()
                if not isinstance(payload, str):
                    raise RuntimeError("language server websocket expects text frames")
                stdin.write(encode_lsp_rpc_frame(payload))
                await stdin.drain()

        async def server_to_client() -> None:
            while True:
                message = await read_lsp_rpc_frame(stdout)
                _arm_idle()
                await connection.send(message)

        try:
            _ = await asyncio.gather(client_to_server(), server_to_client())
        finally:
            _request_shutdown()

    port_file = root / BRIDGE_PORT_FILENAME
    try:
        async with serve(handler, "127.0.0.1", 0) as server:
            server_holder.append(server)
            sockets = server.sockets
            if not sockets:
                raise RuntimeError("language server bridge has no listening socket")
            port_raw = listening_tcp_port(sockets[0], label="language server bridge")
            _ = port_file.write_text(str(port_raw), encoding="utf-8")
            logger.info("code_lsp.bridge_listen", session_id=session_id, port=port_raw)
            _arm_idle()
            await server.wait_closed()
    finally:
        port_file.unlink(missing_ok=True)
        if process.returncode is None:
            process.terminate()
            try:
                _ = await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                _ = await process.wait()


def main() -> None:
    session_id, root, command = bridge_invocation(sys.argv)
    asyncio.run(_run_bridge(session_id, root, command))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _ = sys.stderr.write(f"code_lsp.bridge_failed: {exc}\n")
        raise
