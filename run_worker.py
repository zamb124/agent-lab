#!/usr/bin/env python3
"""
Скрипт запуска TaskIQ Worker.

Используется в Docker для запуска воркера задач.
"""

import os


if __name__ == "__main__":
    # Запуск taskiq worker
    os.execvp(
        "taskiq",
        ["taskiq", "worker", "apps.worker:broker", "--workers", "4"]
    )

