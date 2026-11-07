"""Вызов figma-console-mcp без MCP-реестра.

``uv run python -m scripts.tools.figma_mcp <команда>`` поднимает
``npx figma-console-mcp@<pin>`` по stdio (pin читается из
``.cursor/mcp.json``), выполняет вызовы и гасит процесс. Desktop Bridge
плагин переподключается к новому экземпляру на том же порту, поэтому
одноразовые запуски не ломают сессию моста.

Команды:

- ``list`` — все инструменты сервера;
- ``call <tool> '<json>'`` — один вызов ``tools/call``;
- ``batch <file>`` — пакет вызовов: JSON-список ``[{"name", "arguments"}]``
  или JSONL ``{"name", "arguments"}``;
- ``status`` — ``figma_get_status`` с ``probe: true``;
- ``--wait-plugin SECONDS`` — перед вызовами поллить ``figma_get_status``,
  пока ``transport.active`` не станет ``websocket``.

``--raw`` печатает полный JSON-RPC конверт; без флага — только
``content[].text`` (внутренний JSON разворачивается).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_JSON = REPO_ROOT / ".cursor" / "mcp.json"
DEFAULT_PIN = "1.46.0"
PLUGIN_MANIFEST = Path.home() / ".figma-console-mcp" / "plugin" / "manifest.json"


def _server_argv() -> list[str]:
    pin = DEFAULT_PIN
    try:
        cfg = json.loads(MCP_JSON.read_text())
        args: list[str] = cfg["mcpServers"]["figma-console"]["args"]
        for arg in args:
            m = re.fullmatch(r"figma-console-mcp@(.+)", arg)
            if m:
                pin = m.group(1)
    except Exception:
        pass
    return ["npx", "-y", f"figma-console-mcp@{pin}"]


class _Server:
    def __init__(self) -> None:
        self._proc = subprocess.Popen(
            _server_argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=dict(os.environ),
        )
        self._id = 0

    def _send(self, obj: dict) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _recv(self, rid: int, timeout: float) -> dict:
        assert self._proc.stdout is not None
        end = time.time() + timeout
        while time.time() < end:
            ready, _, _ = select.select([self._proc.stdout], [], [], 1.0)
            if not ready:
                continue
            line = self._proc.stdout.readline()
            if not line:
                return {"error": "server closed stdout"}
            try:
                obj = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if obj.get("id") == rid:
                return obj
        return {"error": "timeout"}

    def call(self, method: str, params: dict, timeout: float = 280) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        return self._recv(self._id, timeout)

    def start(self) -> bool:
        resp = self.call(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-lab figma_mcp", "version": "1.0"},
            },
            timeout=120,
        )
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        time.sleep(0.3)
        return "result" in resp

    def tool(self, name: str, arguments: dict) -> dict:
        return self.call("tools/call", {"name": name, "arguments": arguments})

    def stop(self) -> None:
        self._proc.terminate()


def _status_active(resp: dict) -> str | None:
    for item in resp.get("result", {}).get("content", []):
        try:
            data = json.loads(item.get("text", "{}"))
        except json.JSONDecodeError:
            continue
        active = data.get("transport", {}).get("active")
        if active:
            return str(active)
    return None


def _wait_plugin(server: _Server, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        active = _status_active(server.tool("figma_get_status", {"probe": True}))
        if active == "websocket":
            return True
        print(
            f"[wait-plugin] transport={active or 'none'} — "
            f"запустите Desktop Bridge в Figma ({PLUGIN_MANIFEST})",
            file=sys.stderr,
        )
        time.sleep(3)
    return False


def _emit(resp: dict, raw: bool) -> None:
    if raw:
        print(json.dumps(resp, ensure_ascii=False, indent=1))
        return
    for item in resp.get("result", {}).get("content", []):
        text = item.get("text", "")
        try:
            print(json.dumps(json.loads(text), ensure_ascii=False, indent=1))
        except json.JSONDecodeError:
            print(text)
    if "result" not in resp:
        print(json.dumps(resp, ensure_ascii=False, indent=1))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    _ = parser.add_argument("command", choices=["list", "call", "batch", "status"])
    _ = parser.add_argument("name", nargs="?", help="tool name (call)")
    _ = parser.add_argument("args", nargs="?", help="JSON args (call) or batch file")
    _ = parser.add_argument("--raw", action="store_true", help="full JSON-RPC envelope")
    _ = parser.add_argument(
        "--wait-plugin",
        type=float,
        default=0,
        metavar="SECONDS",
        help="poll figma_get_status until bridge connects",
    )
    ns = parser.parse_args()

    server = _Server()
    try:
        if not server.start():
            print("figma-console-mcp не инициализировался", file=sys.stderr)
            return 2
        if ns.wait_plugin and not _wait_plugin(server, ns.wait_plugin):
            return 3
        if ns.command == "list":
            resp = server.call("tools/list", {})
            for tool in resp.get("result", {}).get("tools", []):
                print(tool["name"])
            return 0
        if ns.command == "status":
            _emit(server.tool("figma_get_status", {"probe": True}), ns.raw)
            return 0
        if ns.command == "call":
            if not ns.name:
                parser.error("call требует имя инструмента")
            _emit(server.tool(ns.name, json.loads(ns.args or "{}")), ns.raw)
            return 0
        if not ns.args:
            parser.error("batch требует файл с вызовами")
        text = Path(ns.args).read_text()
        batch = json.loads(text) if ns.args.endswith(".json") else [
            json.loads(line) for line in text.splitlines() if line.strip()
        ]
        for item in batch:
            print(f"=== {item['name']} ===")
            _emit(server.tool(item["name"], item.get("arguments", {})), ns.raw)
        return 0
    finally:
        server.stop()


if __name__ == "__main__":
    sys.exit(main())
