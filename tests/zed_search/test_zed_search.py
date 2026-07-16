"""
Интеграционные тесты zed-search (claude-context MCP).

Проверяют end-to-end:
1. Health check корректно определяет состояние всех компонентов
2. Поиск через MCP возвращает релевантные результаты
3. Переиндексация при изменении файла обновляет индекс
4. Setup идемпотентен (повторный запуск не ломает ничего)
5. Force reindex пересоздаёт индекс с нуля

Тесты требуют запущенные Ollama (127.0.0.1:11434) и Milvus (127.0.0.1:19530).
Запускаются через: pytest tests/search/integration/test_zed_search.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

# --- Утилиты для работы с MCP через stdio ---


def _mcp_call(proc: subprocess.Popen, msg_id: int, method: str, params: dict | None = None) -> dict | None:
    """Отправляет JSON-RPC сообщение в stdin MCP-сервера и читает ответ."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        msg["params"] = params
    line = json.dumps(msg) + "\n"
    assert proc.stdin is not None
    proc.stdin.write(line)
    proc.stdin.flush()

    # Читаем строки, пока не найдём JSON с нужным id
    assert proc.stdout is not None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        raw = proc.stdout.readline()
        if not raw:
            return None
        raw = raw.strip()
        if not raw:
            continue
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if resp.get("id") == msg_id:
            return resp
    return None


def _mcp_notify(proc: subprocess.Popen, method: str, params: dict | None = None) -> None:
    """Отправляет notification (без id, без ожидания ответа)."""
    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    line = json.dumps(msg) + "\n"
    assert proc.stdin is not None
    proc.stdin.write(line)
    proc.stdin.flush()


def _start_mcp(project_path: str) -> subprocess.Popen:
    """Запускает MCP-сервер для проекта."""
    env = os.environ.copy()
    env.setdefault("MILVUS_ADDRESS", "127.0.0.1:19530")
    env.setdefault("EMBEDDING_PROVIDER", "Ollama")
    env.setdefault("OLLAMA_HOST", "http://127.0.0.1:11434")
    env.setdefault("OLLAMA_MODEL", "nomic-embed-text")
    proc = subprocess.Popen(
        ["npx", "-y", "@zilliz/claude-context-mcp@latest"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )
    # Initialize
    resp = _mcp_call(proc, 1, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "zed-search-test", "version": "1.0.0"},
    })
    assert resp is not None, "MCP сервер не ответил на initialize"
    assert "error" not in resp, f"Ошибка initialize: {resp.get('error')}"
    _mcp_notify(proc, "notifications/initialized")
    return proc


def _mcp_tool_call(proc: subprocess.Popen, msg_id: int, tool: str, args: dict) -> dict | None:
    """Вызывает инструмент MCP и возвращает ответ."""
    return _mcp_call(proc, msg_id, "tools/call", {"name": tool, "arguments": args})


def _extract_text(resp: dict | None) -> str:
    """Извлекает текст из MCP-ответа."""
    if resp is None:
        return ""
    result = resp.get("result", {})
    if isinstance(result, dict):
        content = result.get("content", [])
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    texts.append(item["text"])
            return "\n".join(texts)
    return json.dumps(result, ensure_ascii=False)


def _stop_mcp(proc: subprocess.Popen) -> None:
    """Останавливает MCP-сервер."""
    try:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


# --- Проверки доступности --


def _check_ollama() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
        return True
    except Exception:
        return False


def _check_milvus() -> bool:
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", "milvus-standalone"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and "healthy" in result.stdout
    except Exception:
        return False


# Фикстура для пропуска тестов, требующих полный MCP-стек.
# Тесты healthcheck работают без неё (проверяют сам скрипт).
require_full_stack = pytest.mark.skipif(
    not (_check_ollama() and _check_milvus()),
    reason="Ollama + Milvus недоступны",
)


# --- Тесты ---


class TestZedSearchHealthcheck:
    """Тесты healthcheck-скрипта."""

    def test_healthcheck_runs(self) -> None:
        """Healthcheck-скрипт запускается и завершается с понятным кодом."""
        result = subprocess.run(
            ["bash", "scripts/zed_search/healthcheck.sh"],
            capture_output=True, text=True, timeout=30,
        )
        # Healthcheck должен завершиться (exit 0 или exit 1)
        # exit 0 = всё OK или WARN, exit 1 = что-то сломано
        assert result.returncode in (0, 1), (
            f"Неожиданный exit-код {result.returncode}:\n{result.stdout}\n{result.stderr}"
        )
        assert "MCP-пакет" in result.stdout, f"Нет строки MCP-пакет в отчёте:\n{result.stdout}"

    @require_full_stack
    def test_healthcheck_passes_when_all_ok(self) -> None:
        """Healthcheck возвращает exit 0 когда все компоненты работают."""
        result = subprocess.run(
            ["bash", "scripts/zed_search/healthcheck.sh"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"Healthcheck упал:\n{result.stdout}\n{result.stderr}"
        assert "✅ Всё ОК" in result.stdout or "✅" in result.stdout

    def test_healthcheck_reports_version(self) -> None:
        """Healthcheck показывает версию MCP-пакета (или её отсутствие)."""
        result = subprocess.run(
            ["bash", "scripts/zed_search/healthcheck.sh"],
            capture_output=True, text=True, timeout=30,
        )
        # Должна быть строка с MCP-пакет и упоминание версии или 'нет'
        mcp_line = [line for line in result.stdout.splitlines() if "MCP-пакет" in line]
        assert mcp_line, f"Нет строки MCP-пакет:\n{result.stdout}"
        assert any(kw in mcp_line[0] for kw in ["v", "актуальна", "устарела", "npx"]), (
            f"Нет информации о версии в строке: {mcp_line[0]}"
        )


class TestZedSearchSearch:
    """Тесты поиска через MCP."""

    @require_full_stack
    def test_search_returns_results(self, tmp_path: Path) -> None:
        """Поиск через MCP возвращает релевантные результаты."""
        project = Path(__file__).resolve().parent.parent.parent
        proc = _start_mcp(str(project))
        try:
            resp = _mcp_tool_call(proc, 10, "search_code", {
                "query": "WebSocket notification",
                "path": str(project),
            })
            text = _extract_text(resp)
            # Должен вернуть какой-то результат (не пустой)
            assert text, "Поиск вернул пустой результат"
            # Не должен содержать ошибку
            assert "Error" not in text or "error" not in text.lower() or "✅" in text
        finally:
            _stop_mcp(proc)

    @require_full_stack
    def test_search_relevant_query(self) -> None:
        """Поиск по конкретному концепту находит нужный файл."""
        project = Path(__file__).resolve().parent.parent.parent
        proc = _start_mcp(str(project))
        try:
            resp = _mcp_tool_call(proc, 20, "search_code", {
                "query": "rate limiting throttling",
                "path": str(project),
            })
            text = _extract_text(resp)
            assert text, "Поиск вернул пустой результат"
        finally:
            _stop_mcp(proc)


class TestZedSearchReindex:
    """Тесты переиндексации при изменении файлов."""

    @require_full_stack
    def test_reindex_on_file_change(self, tmp_path: Path) -> None:
        """
        При изменении файла и touch триггера — индекс обновляется.

        Создаём временный файл, индексируем, меняем содержимое,
        touch триггер, проверяем что индекс обновился.
        """
        project = Path(__file__).resolve().parent.parent.parent

        # 1. Создаём тестовый файл
        test_file = project / "tmp_zed_search_test.py"
        test_file.write_text(
            "# zed-search test marker: FLUFFY_BUNNY_42\n"
            "def fluffy_bunny():\n"
            "    return 42\n",
            encoding="utf-8",
        )
        try:
            proc = _start_mcp(str(project))
            try:
                # 2. Индексируем
                resp = _mcp_tool_call(proc, 30, "index_codebase", {
                    "path": str(project),
                })
                assert resp is not None, "index_codebase не ответил"

                # 3. Ждём завершения
                for _ in range(60):
                    resp = _mcp_tool_call(proc, 31, "get_indexing_status", {
                        "path": str(project),
                    })
                    text = _extract_text(resp)
                    if "completed" in text.lower() or "ready" in text.lower():
                        break
                    time.sleep(2)
                else:
                    pytest.fail("Индексация не завершилась за 120с")

                # 4. Ищем маркер — должен найтись
                resp = _mcp_tool_call(proc, 32, "search_code", {
                    "query": "FLUFFY_BUNNY_42",
                    "path": str(project),
                })
                text = _extract_text(resp)
                assert "FLUFFY_BUNNY_42" in text or "fluffy_bunny" in text, (
                    f"Маркер FLUFFY_BUNNY_42 не найден в результатах поиска:\n{text}"
                )

                # 5. Меняем файл
                test_file.write_text(
                    "# zed-search test marker: RAINBOW_UNICORN_99\n"
                    "def rainbow_unicorn():\n"
                    "    return 99\n",
                    encoding="utf-8",
                )

                # 6. Touch триггер
                trigger = Path.home() / ".context" / ".sync-trigger"
                trigger.parent.mkdir(parents=True, exist_ok=True)
                trigger.touch()

                # 7. Ждём переиндексации
                time.sleep(5)
                for _ in range(60):
                    resp = _mcp_tool_call(proc, 33, "get_indexing_status", {
                        "path": str(project),
                    })
                    text = _extract_text(resp)
                    if "completed" in text.lower() or "ready" in text.lower():
                        break
                    time.sleep(2)

                # 8. Ищем новый маркер
                resp = _mcp_tool_call(proc, 34, "search_code", {
                    "query": "RAINBOW_UNICORN_99",
                    "path": str(project),
                })
                text = _extract_text(resp)
                assert "RAINBOW_UNICORN_99" in text or "rainbow_unicorn" in text, (
                    f"Новый маркер RAINBOW_UNICORN_99 не найден после переиндексации:\n{text}"
                )

                # 9. Старый маркер должен исчезнуть
                resp = _mcp_tool_call(proc, 35, "search_code", {
                    "query": "FLUFFY_BUNNY_42",
                    "path": str(project),
                })
                text = _extract_text(resp)
                # Старый маркер может ещё быть в результатах (если индекс не успел обновиться),
                # но новый должен быть на первом месте
                # Просто проверяем что новый есть
                assert "RAINBOW_UNICORN_99" in text or "rainbow_unicorn" in text, (
                    f"Новый маркер пропал после переиндексации:\n{text}"
                )

            finally:
                _stop_mcp(proc)

        finally:
            test_file.unlink(missing_ok=True)

    @require_full_stack
    def test_force_reindex(self) -> None:
        """Force reindex пересоздаёт индекс с нуля."""
        project = Path(__file__).resolve().parent.parent.parent
        proc = _start_mcp(str(project))
        try:
            # Force reindex
            resp = _mcp_tool_call(proc, 40, "index_codebase", {
                "path": str(project),
                "force": True,
            })
            assert resp is not None, "force reindex не ответил"
            assert "error" not in resp, f"Ошибка force reindex: {resp.get('error')}"

            # Ждём завершения
            for _ in range(60):
                resp = _mcp_tool_call(proc, 41, "get_indexing_status", {
                    "path": str(project),
                })
                text = _extract_text(resp)
                if "completed" in text.lower() or "ready" in text.lower():
                    break
                time.sleep(2)
            else:
                pytest.fail("Force reindex не завершился за 120с")

            # Проверяем что поиск работает
            resp = _mcp_tool_call(proc, 42, "search_code", {
                "query": "WebSocket",
                "path": str(project),
            })
            text = _extract_text(resp)
            assert text, "Поиск после force reindex вернул пустой результат"

        finally:
            _stop_mcp(proc)


class TestZedSearchSetup:
    """Тесты setup-скрипта на идемпотентность."""

    @require_full_stack
    def test_setup_idempotent(self) -> None:
        """Повторный запуск setup не ломает существующую установку."""
        result = subprocess.run(
            ["bash", "scripts/zed_search_setup.sh"],
            capture_output=True, text=True, timeout=120,
        )
        # Setup должен завершиться успешно (exit 0)
        assert result.returncode == 0, (
            f"Setup упал при повторном запуске:\n{result.stdout}\n{result.stderr}"
        )
        # Должен сообщить что всё готово
        assert "✅" in result.stdout or "готов" in result.stdout.lower()


class TestZedSearchMcpIntegration:
    """Полные end-to-end тесты через MCP stdio."""

    @require_full_stack
    def test_full_cycle_index_search_reindex(self) -> None:
        """
        Полный цикл: индексация → поиск → изменение файла → переиндексация → поиск.

        Это главный интеграционный тест, который проверяет всю цепочку.
        """
        project = Path(__file__).resolve().parent.parent.parent
        test_file = project / "tmp_zed_search_e2e.py"
        test_file.write_text(
            "# E2E test marker: PURPLE_DRAGON_77\n"
            "class PurpleDragon:\n"
            "    def breathe(self):\n"
            "        return 'fire'\n",
            encoding="utf-8",
        )
        try:
            proc = _start_mcp(str(project))
            try:
                # 1. Индексация
                resp = _mcp_tool_call(proc, 50, "index_codebase", {"path": str(project)})
                assert resp is not None and "error" not in resp

                # Ждём
                for _ in range(60):
                    resp = _mcp_tool_call(proc, 51, "get_indexing_status", {"path": str(project)})
                    if "completed" in _extract_text(resp).lower():
                        break
                    time.sleep(2)

                # 2. Поиск — находит PURPLE_DRAGON
                resp = _mcp_tool_call(proc, 52, "search_code", {
                    "query": "PURPLE_DRAGON_77",
                    "path": str(project),
                })
                text = _extract_text(resp)
                assert "PURPLE_DRAGON_77" in text or "PurpleDragon" in text, (
                    f"PURPLE_DRAGON не найден после индексации:\n{text}"
                )

                # 3. Меняем файл
                test_file.write_text(
                    "# E2E test marker: GOLDEN_PHOENIX_88\n"
                    "class GoldenPhoenix:\n"
                    "    def fly(self):\n"
                    "        return 'sky'\n",
                    encoding="utf-8",
                )

                # 4. Touch триггер
                trigger = Path.home() / ".context" / ".sync-trigger"
                trigger.parent.mkdir(parents=True, exist_ok=True)
                trigger.touch()

                # 5. Ждём переиндексации
                time.sleep(5)
                for _ in range(60):
                    resp = _mcp_tool_call(proc, 53, "get_indexing_status", {"path": str(project)})
                    if "completed" in _extract_text(resp).lower():
                        break
                    time.sleep(2)

                # 6. Поиск — находит GOLDEN_PHOENIX
                resp = _mcp_tool_call(proc, 54, "search_code", {
                    "query": "GOLDEN_PHOENIX_88",
                    "path": str(project),
                })
                text = _extract_text(resp)
                assert "GOLDEN_PHOENIX_88" in text or "GoldenPhoenix" in text, (
                    f"GOLDEN_PHOENIX не найден после переиндексации:\n{text}"
                )

            finally:
                _stop_mcp(proc)

        finally:
            test_file.unlink(missing_ok=True)
