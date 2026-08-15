"""Stdio JSON-RPC кадры language server и файлы LSP-bridge."""

from __future__ import annotations

import asyncio

from core.logging import get_logger

logger = get_logger(__name__)

BRIDGE_PORT_FILENAME = "bridge.port"
BRIDGE_PID_FILENAME = "bridge.pid"


def encode_lsp_rpc_frame(payload: str) -> bytes:
    body = payload.encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


async def read_lsp_rpc_frame(reader: asyncio.StreamReader) -> str:
    content_length: int | None = None
    while True:
        line = await reader.readline()
        if not line:
            raise ConnectionError("language server closed stdout")
        if line in {b"\r\n", b"\n"}:
            break
        decoded = line.decode("ascii")
        if decoded.lower().startswith("content-length:"):
            content_length = int(decoded.split(":", 1)[1].strip())
    if content_length is None:
        raise RuntimeError("LSP message missing Content-Length")
    body = await reader.readexactly(content_length)
    return body.decode("utf-8")


async def drain_lsp_stderr(process: asyncio.subprocess.Process, session_id: str) -> None:
    if process.stderr is None:
        return
    while True:
        line = await process.stderr.readline()
        if not line:
            return
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            logger.debug("code_lsp.stderr", session_id=session_id, line=text)
