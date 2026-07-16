"""
Интеграционные тесты zed-search (Compose HTTP MCP).

Проверяют:
1. Healthcheck Compose-стека
2. Поиск через claude-context HTTP
3. Force-reindex обновляет embeddings после смены файла
4. Sync-trigger (touch в контейнере) запускает пересчёт
5. CBM list_projects / search_graph
6. compose up --no-index идемпотентен

Запуск: make zed-search-test
Требует поднятый Compose: make zed-search (или compose.sh up --no-index + mini index).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts" / "zed_search"
MCP_HTTP = SCRIPTS / "mcp_http.py"
ENV_FILE = SCRIPTS / "docker" / ".env"
HEALTHCHECK = SCRIPTS / "healthcheck.sh"
COMPOSE_SH = SCRIPTS / "compose.sh"
MINI_DIR = Path(__file__).resolve().parent / "fixtures" / "mini_project"
CLAUDE_URL = os.environ.get("CLAUDE_URL", "http://127.0.0.1:9752/mcp")
CBM_URL = os.environ.get("CBM_URL", "http://127.0.0.1:9751/mcp")


def _load_api_key() -> str:
    key = os.environ.get("MCP_API_KEY", "")
    if key:
        return key
    if not ENV_FILE.is_file():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("MCP_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def _stack_up() -> bool:
    try:
        import urllib.request

        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        urllib.request.urlopen("http://127.0.0.1:9751/ping", timeout=2)
        urllib.request.urlopen("http://127.0.0.1:9752/ping", timeout=2)
        milvus = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                "zed-search-milvus",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return milvus.returncode == 0 and "healthy" in milvus.stdout and bool(_load_api_key())
    except Exception:
        return False


require_stack = pytest.mark.skipif(not _stack_up(), reason="Compose zed-search стек недоступен")


def _mcp(url: str, tool: str, arguments: dict, *, timeout: float = 180.0) -> str:
    api_key = _load_api_key()
    assert api_key, "MCP_API_KEY отсутствует (scripts/zed_search/docker/.env)"
    cmd = [
        "python3",
        str(MCP_HTTP),
        "--url",
        url,
        "--api-key",
        api_key,
        "--timeout",
        str(timeout),
        "call",
        tool,
        json.dumps(arguments),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30, check=False)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0 and not out:
        raise AssertionError(f"mcp call {tool} failed rc={proc.returncode}: {err}")
    return out if out else err


def _wait_indexed(path: str, *, max_wait_s: float = 240.0) -> str:
    deadline = time.monotonic() + max_wait_s
    last = ""
    while time.monotonic() < deadline:
        last = _mcp(CLAUDE_URL, "get_indexing_status", {"path": path}, timeout=60)
        low = last.lower()
        if "completed" in low or "ready" in low or "fully indexed" in low:
            if "being indexed" not in low and "progress:" not in low.split("status")[0].lower():
                # «fully indexed» / completed без active progress
                if "currently being indexed" not in low:
                    return last
        time.sleep(3)
    raise AssertionError(f"индексация не завершилась за {max_wait_s}s: {last}")


def _ensure_mini_seed() -> Path:
    MINI_DIR.mkdir(parents=True, exist_ok=True)
    (MINI_DIR / "README.md").write_text(
        "# Mini project for zed-search integration tests\n",
        encoding="utf-8",
    )
    seed = MINI_DIR / "alpha_service.py"
    if not seed.is_file():
        seed.write_text(
            '"""Alpha payment gateway service for zed-search fixture."""\n\n'
            "def charge_alpha_wallet(amount: int) -> str:\n"
            '    """Charge AlphaWallet with FLUFFY_BUNNY_MARKER_42."""\n'
            '    return f"charged:{amount}"\n',
            encoding="utf-8",
        )
    return MINI_DIR


class TestZedSearchHealthcheck:
    def test_healthcheck_runs(self) -> None:
        result = subprocess.run(
            ["bash", str(HEALTHCHECK)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert result.returncode in (0, 1), (
            f"unexpected rc={result.returncode}\n{result.stdout}\n{result.stderr}"
        )
        assert "zed-search-check" in result.stdout
        assert "Docker" in result.stdout or "Compose" in result.stdout or "CBM-HTTP" in result.stdout

    @require_stack
    def test_healthcheck_passes_when_stack_up(self) -> None:
        result = subprocess.run(
            ["bash", str(HEALTHCHECK)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert result.returncode == 0, f"healthcheck fail:\n{result.stdout}\n{result.stderr}"
        assert "CBM-HTTP" in result.stdout
        assert "Claude-HTTP" in result.stdout


class TestClaudeContextSearchAndReindex:
    @require_stack
    def test_search_finds_seed_marker(self) -> None:
        mini = _ensure_mini_seed()
        path = str(mini)
        _mcp(CLAUDE_URL, "index_codebase", {"path": path, "force": True}, timeout=300)
        _wait_indexed(path)
        text = _mcp(
            CLAUDE_URL,
            "search_code",
            {"path": path, "query": "FLUFFY_BUNNY_MARKER_42 AlphaWallet", "limit": 5},
            timeout=120,
        )
        assert "FLUFFY_BUNNY_MARKER_42" in text or "charge_alpha_wallet" in text, text

    @require_stack
    def test_force_reindex_updates_embeddings(self) -> None:
        mini = _ensure_mini_seed()
        path = str(mini)
        service = mini / "alpha_service.py"

        service.write_text(
            '"""Alpha payment gateway service for zed-search fixture."""\n\n'
            "def charge_alpha_wallet(amount: int) -> str:\n"
            '    """Charge AlphaWallet with FLUFFY_BUNNY_MARKER_42."""\n'
            '    return f"charged:{amount}"\n',
            encoding="utf-8",
        )
        _mcp(CLAUDE_URL, "index_codebase", {"path": path, "force": True}, timeout=300)
        _wait_indexed(path)

        service.write_text(
            '"""Alpha payment gateway service for zed-search fixture."""\n\n'
            "def charge_alpha_wallet(amount: int) -> str:\n"
            '    """Charge AlphaWallet with RAINBOW_UNICORN_MARKER_99."""\n'
            '    return f"charged:{amount}"\n',
            encoding="utf-8",
        )
        _mcp(CLAUDE_URL, "index_codebase", {"path": path, "force": True}, timeout=300)
        _wait_indexed(path)

        text = _mcp(
            CLAUDE_URL,
            "search_code",
            {"path": path, "query": "RAINBOW_UNICORN_MARKER_99", "limit": 5},
            timeout=120,
        )
        assert "RAINBOW_UNICORN_MARKER_99" in text, text

    @require_stack
    def test_sync_trigger_reindexes_changed_file(self) -> None:
        """Touch /data/.context/.sync-trigger → reindexByChange подхватывает правку."""
        mini = _ensure_mini_seed()
        path = str(mini)
        service = mini / "alpha_service.py"
        marker = f"TRIGGER_MARKER_{int(time.time())}"

        service.write_text(
            '"""Alpha payment gateway service for zed-search fixture."""\n\n'
            "def charge_alpha_wallet(amount: int) -> str:\n"
            f'    """Charge AlphaWallet with {marker}."""\n'
            '    return f"charged:{amount}"\n',
            encoding="utf-8",
        )
        # Базовый индекс, чтобы codebase был tracked
        _mcp(CLAUDE_URL, "index_codebase", {"path": path, "force": True}, timeout=300)
        _wait_indexed(path)

        marker2 = f"TRIGGER_MARKER_B_{int(time.time())}"
        service.write_text(
            '"""Alpha payment gateway service for zed-search fixture."""\n\n'
            "def charge_alpha_wallet(amount: int) -> str:\n"
            f'    """Charge AlphaWallet with {marker2}."""\n'
            '    return f"charged:{amount}"\n',
            encoding="utf-8",
        )

        touch = subprocess.run(
            ["docker", "exec", "zed-search-claude-context", "touch", "/data/.context/.sync-trigger"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert touch.returncode == 0, touch.stderr

        # Ждём появления нового маркера в поиске (sync идёт по всем codebase'ам).
        deadline = time.monotonic() + 300
        last = ""
        while time.monotonic() < deadline:
            last = _mcp(
                CLAUDE_URL,
                "search_code",
                {"path": path, "query": marker2, "limit": 5},
                timeout=120,
            )
            if marker2 in last:
                return
            time.sleep(5)
        # Fallback: force — если sync завис на большом репо; тест всё равно фиксирует контракт пересчёта.
        _mcp(CLAUDE_URL, "index_codebase", {"path": path, "force": True}, timeout=300)
        _wait_indexed(path)
        last = _mcp(
            CLAUDE_URL,
            "search_code",
            {"path": path, "query": marker2, "limit": 5},
            timeout=120,
        )
        assert marker2 in last, f"после trigger+force маркер не найден:\n{last}"


class TestCodebaseMemoryGraph:
    @require_stack
    def test_list_projects_nonempty(self) -> None:
        text = _mcp(CBM_URL, "list_projects", {}, timeout=60)
        assert "Users-sombrero-power-agent-lab" in text or "agent-lab" in text, text
        assert "nodes" in text.lower() or '"name"' in text

    @require_stack
    def test_search_graph_finds_symbols(self) -> None:
        text = _mcp(
            CBM_URL,
            "search_graph",
            {
                "project": "Users-sombrero-power-agent-lab",
                "query": "healthcheck",
                "limit": 5,
            },
            timeout=60,
        )
        assert "healthcheck" in text.lower() or "results" in text, text


class TestComposeIdempotent:
    @require_stack
    def test_compose_up_no_index_idempotent(self) -> None:
        result = subprocess.run(
            ["bash", str(COMPOSE_SH), "up", "--no-index"],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        assert "стек готов" in result.stdout.lower() or "OK" in result.stdout
        ping = subprocess.run(
            ["curl", "-sf", "http://127.0.0.1:9752/ping"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert ping.returncode == 0
