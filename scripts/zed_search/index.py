#!/usr/bin/env python3
"""Первичная / принудительная индексация через HTTP MCP (Compose-стек).

Использование:
    python3 scripts/zed_search/index.py [путь_к_проекту]
    python3 scripts/zed_search/index.py --force [путь]

Читает MCP_API_KEY и URL из scripts/zed_search/docker/.env (или env).
Не спавнит stdio MCP — только HTTP к уже запущенному compose-прокси.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MCP_HTTP = SCRIPT_DIR / "mcp_http.py"
ENV_FILE = SCRIPT_DIR / "docker" / ".env"
DEFAULT_CLAUDE_URL = "http://127.0.0.1:9752/mcp"


def load_dotenv(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip()] = val.strip()
    return out


def log(msg: str) -> None:
    print(f"[zed-search-index] {msg}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=os.getcwd())
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--max-wait-s", type=float, default=900.0)
    args = parser.parse_args()

    project_path = str(Path(args.path).resolve())
    dotenv = load_dotenv(ENV_FILE)
    api_key = args.api_key or os.environ.get("MCP_API_KEY") or dotenv.get("MCP_API_KEY", "")
    url = args.url or os.environ.get("CLAUDE_URL") or DEFAULT_CLAUDE_URL
    if not api_key:
        log("нет MCP_API_KEY — запусти: make zed-search (или compose.sh ensure-env)")
        return 1
    if not MCP_HTTP.is_file():
        log(f"нет {MCP_HTTP}")
        return 1

    log(f"путь: {project_path}")
    log(f"url: {url}")
    payload = {"path": project_path, "force": bool(args.force)}
    cmd = [
        sys.executable,
        str(MCP_HTTP),
        "--url",
        url,
        "--api-key",
        api_key,
        "--timeout",
        str(max(args.max_wait_s, 60.0)),
        "call",
        "index_codebase",
        __import__("json").dumps(payload),
        "--wait-status",
        "--status-path",
        project_path,
        "--max-wait-s",
        str(args.max_wait_s),
    ]
    proc = subprocess.run(cmd, check=False)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
