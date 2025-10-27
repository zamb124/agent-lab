#!/usr/bin/env python3
"""
Скрипт запуска Agents Lab в продакшн режиме с Gunicorn.
Используется в Docker для запуска нескольких воркеров.
"""

import os
import multiprocessing
from app.core.config import settings

if __name__ == "__main__":
    # Определяем количество воркеров на основе CPU cores
    if settings.server.workers == 4:  # Если не переопределено в конфиге
        cpu_count = multiprocessing.cpu_count()
        workers = min(cpu_count * 2 + 1, 8)  # Максимум 8 воркеров
    else:
        workers = settings.server.workers

    print("🚀 Запуск Agents Lab в продакшн режиме...")
    print(f"📍 Адрес: http://{settings.server.host}:{settings.server.port}")
    print(f"💻 CPU cores: {multiprocessing.cpu_count()}")
    print(f"🔧 Воркеров: {workers}")
    print(f"🏭 Worker class: {settings.server.worker_class}")

    # Параметры для gunicorn
    gunicorn_cmd = [
        "gunicorn",
        "--bind", f"{settings.server.host}:{settings.server.port}",
        "--workers", str(workers),
        "--worker-class", settings.server.worker_class,
        "--worker-connections", str(settings.server.worker_connections),
        "--max-requests", str(settings.server.max_requests),
        "--max-requests-jitter", str(settings.server.max_requests_jitter),
        "--timeout", str(settings.server.timeout),
        "--keep-alive", str(settings.server.keepalive),
        "--log-level", "info",
        "--access-logfile", "-",
        "--error-logfile", "-",
        "app.main:app"
    ]

    # Запускаем gunicorn
    os.execvp("gunicorn", gunicorn_cmd)
