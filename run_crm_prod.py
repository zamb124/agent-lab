#!/usr/bin/env python3
"""
Скрипт запуска CRM Service в продакшн режиме с Gunicorn.
"""

import os
import multiprocessing
from pathlib import Path

from core.config.loader import load_merged_config
from core.config import BaseSettings


if __name__ == "__main__":
    project_root = Path(__file__).parent
    service_config_path = project_root / "apps" / "crm" / "conf.json"
    
    merged_config = load_merged_config(
        base_config_path=project_root / "conf.json",
        service_config_path=service_config_path
    )
    
    settings = BaseSettings(**merged_config)
    
    cpu_count = multiprocessing.cpu_count()
    if settings.server.workers == 4:
        workers = min(cpu_count * 2 + 1, 8)
    else:
        workers = settings.server.workers

    print("Запуск CRM Service в продакшн режиме...")
    print(f"Адрес: http://{settings.server.host}:{settings.server.port}")
    print(f"CPU cores: {cpu_count}")
    print(f"Воркеров: {workers}")
    print(f"Worker class: {settings.server.worker_class}")

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
        "apps.crm.main:app"
    ]

    os.execvp("gunicorn", gunicorn_cmd)

