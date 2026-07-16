#!/usr/bin/env python3
"""
Первичная индексация кодовой базы через claude-context MCP.

Подключается к MCP-серверу @zillux/claude-context-mcp по stdio,
вызывает инструмент index_codebase, ждёт завершения индексации
и печатает понятный отчёт.

Использование:
    python3 scripts/zed_search_index.py [путь_к_проекту]

Если путь не указан — используется текущая директория.
"""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

# --- Конфигурация ---
MCP_PACKAGE = "@zilliz/claude-context-mcp@latest"
TIMEOUT_START_S = 30   # ожидание ответа на initialize
TIMEOUT_INDEX_S = 30   # ожидание ответа на index_codebase
TIMEOUT_STATUS_S = 30  # ожидание ответа на get_indexing_status
POLL_INTERVAL_S = 5    # интервал опроса статуса
MAX_INDEX_TIME_S = 600  # максимальное время ожидания индексации (10 мин)

ENV_DEFAULTS = {
    "MILVUS_ADDRESS": "127.0.0.1:19530",
    "EMBEDDING_PROVIDER": "Ollama",
    "OLLAMA_HOST": "http://127.0.0.1:11434",
    "OLLAMA_MODEL": "nomic-embed-text",
}


def log(msg: str) -> None:
    print(f"[zed-search-index] {msg}", flush=True)


def send_msg(proc: subprocess.Popen, msg: dict) -> None:
    """Отправляет JSON-RPC сообщение в stdin MCP-сервера."""
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()


def read_msg(proc: subprocess.Popen, timeout: float) -> dict | None:
    """Читает одно JSON-RPC сообщение из stdout MCP-сервера.

    Пропускает строки, которые не являются валидным JSON
    (логи, отладочный вывод и т.д.).
    """
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        ready, _, _ = select.select([proc.stdout], [], [], remaining)
        if not ready:
            return None
        line = proc.stdout.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            # Пропускаем не-JSON строки (логи и т.д.)
            continue


def extract_text(result: dict) -> str:
    """Извлекает текст из result.content MCP-ответа."""
    if not isinstance(result, dict):
        return str(result)
    content = result.get("content")
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
        return "\n".join(texts)
    if isinstance(content, str):
        return content
    return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> int:
    project_path = str(Path(sys.argv[1] if len(sys.argv) > 1 else os.getcwd()).resolve())
    log(f"Путь проекта: {project_path}")

    # --- Подготовка окружения ---
    env = os.environ.copy()
    for key, val in ENV_DEFAULTS.items():
        env.setdefault(key, val)

    # --- Запуск MCP-сервера ---
    log(f"Запуск MCP-сервера ({MCP_PACKAGE})...")
    proc = subprocess.Popen(
        ["npx", "-y", MCP_PACKAGE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )

    try:
        # 1. initialize
        send_msg(proc, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "zed-search-indexer", "version": "1.0.0"},
            },
        })
        resp = read_msg(proc, TIMEOUT_START_S)
        if resp is None:
            log("❌ MCP-сервер не ответил на initialize")
            return 1
        if "error" in resp:
            log(f"❌ Ошибка initialize: {resp['error']}")
            return 1
        log("✅ MCP-сервер инициализирован")

        # 2. notifications/initialized
        send_msg(proc, {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })

        # 3. index_codebase
        log("Запуск index_codebase...")
        send_msg(proc, {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "index_codebase",
                "arguments": {"path": project_path},
            },
        })
        resp = read_msg(proc, TIMEOUT_INDEX_S)
        if resp is None:
            log("❌ MCP-сервер не ответил на index_codebase")
            return 1
        if "error" in resp:
            log(f"❌ Ошибка index_codebase: {resp['error']}")
            return 1

        index_text = extract_text(resp.get("result", {}))
        log(f"Ответ index_codebase: {index_text}")

        # 4. Опрос статуса до завершения
        log("Ожидание завершения индексации...")
        start = time.monotonic()
        last_status = ""
        while time.monotonic() - start < MAX_INDEX_TIME_S:
            send_msg(proc, {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_indexing_status",
                    "arguments": {"path": project_path},
                },
            })
            resp = read_msg(proc, TIMEOUT_STATUS_S)
            if resp is None:
                log("⚠️  Нет ответа на get_indexing_status — продолжаем")
                time.sleep(POLL_INTERVAL_S)
                continue
            if "error" in resp:
                log(f"⚠️  Ошибка get_indexing_status: {resp['error']}")
                time.sleep(POLL_INTERVAL_S)
                continue

            status_text = extract_text(resp.get("result", {}))
            if status_text != last_status:
                log(f"Статус: {status_text}")
                last_status = status_text

            # Проверяем завершение
            if "completed" in status_text.lower() or "ready" in status_text.lower():
                log("✅ Индексация завершена!")
                return 0

            time.sleep(POLL_INTERVAL_S)

        log(f"⚠️  Индексация не завершилась за {MAX_INDEX_TIME_S // 60} мин — продолжается в фоне")
        return 0

    finally:
        proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
