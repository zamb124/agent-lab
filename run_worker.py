#!/usr/bin/env python3
"""
Скрипт запуска TaskIQ Worker.

Используется в Docker для запуска воркера задач.
"""

import os
import sys


if __name__ == "__main__":
    # Запуск taskiq worker
    os.execvp(
        "taskiq",
        ["taskiq", "worker", "core.tasks.worker:broker", "--workers", "1"]
    )

