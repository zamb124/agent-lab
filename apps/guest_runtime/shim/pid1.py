#!/usr/bin/env python3
"""PID1 shim для guest code_agent. Только stdlib."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_context_lock = threading.Lock()
_context: dict[str, Any] | None = None
_listen_lock = threading.Lock()
_listen_proc: subprocess.Popen[str] | None = None
_listen_fingerprint: str | None = None


def _log(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _require_context() -> dict[str, Any]:
    with _context_lock:
        if _context is None:
            raise RuntimeError("POST /context is required before invoke")
        return dict(_context)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length_header = handler.headers.get("Content-Length")
    if length_header is None:
        raise ValueError("Content-Length required")
    length = int(length_header)
    raw = handler.rfile.read(length)
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("JSON object required")
    return parsed


def _write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _argv_from_context(ctx: dict[str, Any]) -> list[str]:
    argv_raw = ctx.get("invoke_argv")
    if not isinstance(argv_raw, list) or len(argv_raw) == 0:
        raise RuntimeError("invoke_argv is required")
    argv: list[str] = []
    for item in argv_raw:
        if not isinstance(item, str) or item.strip() == "":
            raise RuntimeError("invoke_argv items must be non-empty strings")
        argv.append(item)
    return argv


def _env_from_context(ctx: dict[str, Any]) -> dict[str, str]:
    overlay = ctx.get("env")
    if not isinstance(overlay, dict):
        raise RuntimeError("context.env is required")
    env = os.environ.copy()
    for key, value in overlay.items():
        if not isinstance(key, str) or key.strip() == "":
            raise RuntimeError("context.env keys must be non-empty strings")
        if not isinstance(value, str):
            raise RuntimeError(f"context.env[{key}] must be a string")
        env[key] = value
    port = ctx.get("invoke_listen_port")
    if isinstance(port, int) and port >= 1:
        env["GUEST_LISTEN_PORT"] = str(port)
    return env


def _fingerprint_for_listen(ctx: dict[str, Any]) -> str:
    argv = _argv_from_context(ctx)
    port = ctx.get("invoke_listen_port")
    overlay = ctx.get("env")
    if not isinstance(overlay, dict):
        raise RuntimeError("context.env is required")
    env_items = sorted((str(key), str(value)) for key, value in overlay.items())
    return json.dumps({"argv": argv, "port": port, "env": env_items}, separators=(",", ":"))


def _wait_listen_port(port: int, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"a2a listen process exited {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"a2a listen port {port} did not open")


def _stop_listen() -> None:
    global _listen_proc
    global _listen_fingerprint
    with _listen_lock:
        proc = _listen_proc
        _listen_proc = None
        _listen_fingerprint = None
    if proc is None:
        return
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _listen_alive() -> bool:
    with _listen_lock:
        proc = _listen_proc
    return proc is not None and proc.poll() is None


def _start_a2a_listen(ctx: dict[str, Any]) -> None:
    global _listen_proc
    global _listen_fingerprint
    port = ctx.get("invoke_listen_port")
    if not isinstance(port, int) or port < 1:
        raise RuntimeError("invoke_listen_port is required for a2a invoke")
    argv = _argv_from_context(ctx)
    child_env = _env_from_context(ctx)
    fingerprint = _fingerprint_for_listen(ctx)
    _stop_listen()
    proc = subprocess.Popen(
        argv,
        cwd=os.getcwd(),
        env=child_env,
        stdout=sys.stdout,
        stderr=sys.stdout,
        text=True,
    )
    with _listen_lock:
        _listen_proc = proc
        _listen_fingerprint = fingerprint
    _wait_listen_port(port, proc)


def _maybe_refresh_a2a_listen(ctx: dict[str, Any]) -> None:
    fingerprint = _fingerprint_for_listen(ctx)
    with _listen_lock:
        current = _listen_fingerprint
    if _listen_alive() and current == fingerprint:
        return
    _start_a2a_listen(ctx)


def _invoke_cli(ctx: dict[str, Any], text: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    argv = _argv_from_context(ctx)
    argv.append(text)
    child_env = _env_from_context(ctx)
    if metadata is not None:
        child_env["PLATFORM_A2A_METADATA"] = json.dumps(metadata, ensure_ascii=False)
    completed = subprocess.run(
        argv,
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        check=False,
        env=child_env,
    )
    stdout = completed.stdout
    stderr = completed.stderr
    if completed.returncode != 0:
        raise RuntimeError(
            f"guest cli exited {completed.returncode}: {stderr.strip() or stdout.strip()}"
        )
    stripped = stdout.strip()
    if stripped.startswith("{"):
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    return {"text": stdout}


def _invoke_a2a(ctx: dict[str, Any], text: str, metadata: dict[str, Any] | None) -> dict[str, Any]:
    port = ctx.get("invoke_listen_port")
    if not isinstance(port, int) or port < 1:
        raise RuntimeError("invoke_listen_port is required for a2a invoke")
    body: dict[str, Any] = {"text": text}
    if metadata is not None:
        body["metadata"] = metadata
    payload = json.dumps(body).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{port}/invoke",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"a2a listen HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"a2a listen unreachable: {exc}") from exc
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("a2a listen must return a JSON object")
    return parsed


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        _ = format, args

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            _write_json(self, 200, {"ok": True})
            return
        _write_json(self, 404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        global _context
        if self.path == "/context":
            payload = _read_json(self)
            with _context_lock:
                _context = payload
            kind = payload.get("invoke_kind")
            if kind == "a2a":
                _maybe_refresh_a2a_listen(payload)
            _write_json(self, 200, {"ok": True})
            return
        if self.path == "/invoke":
            ctx = _require_context()
            body = _read_json(self)
            text_value = body.get("text")
            if not isinstance(text_value, str):
                raise ValueError("invoke body.text required")
            text = text_value
            metadata_raw = body.get("metadata")
            metadata: dict[str, Any] | None
            if metadata_raw is None:
                metadata = None
            elif isinstance(metadata_raw, dict):
                metadata = metadata_raw
            else:
                raise ValueError("invoke body.metadata must be an object")
            kind = ctx.get("invoke_kind")
            log_base = {
                "request_id": ctx.get("request_id"),
                "trace_id": ctx.get("trace_id"),
                "session_agent": ctx.get("session_id"),
                "session_id": ctx.get("session_id"),
                "task.id": ctx.get("task_id"),
                "task_id": ctx.get("task_id"),
                "context_id": ctx.get("context_id"),
                "flow.id": ctx.get("flow_id"),
                "guest_runtime.id": ctx.get("guest_runtime_id"),
                "guest_lease.id": ctx.get("guest_lease_id"),
            }
            _log({**log_base, "event": "guest.invoke.start"})
            try:
                if kind == "cli":
                    result = _invoke_cli(ctx, text, metadata)
                elif kind == "a2a":
                    result = _invoke_a2a(ctx, text, metadata)
                else:
                    raise RuntimeError("invoke_kind must be cli or a2a")
            except Exception as exc:
                _log({**log_base, "event": "guest.invoke.failed", "error": str(exc)})
                _write_json(self, 500, {"error": str(exc)})
                return
            _log({**log_base, "event": "guest.invoke.done"})
            _write_json(self, 200, result)
            return
        _write_json(self, 404, {"error": "not found"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("0.0.0.0", args.port), _Handler)
    _log({"event": "guest.shim.listen", "port": args.port})
    server.serve_forever()


if __name__ == "__main__":
    main()
