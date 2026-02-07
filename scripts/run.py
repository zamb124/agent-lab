#!/usr/bin/env python3
"""
Универсальный скрипт запуска сервисов для локальной разработки.

Использование:
    python scripts/run.py agents      # Запуск agents сервиса
    python scripts/run.py frontend    # Запуск frontend сервиса
    python scripts/run.py crm         # Запуск crm сервиса
    python scripts/run.py rag         # Запуск rag сервиса
    python scripts/run.py worker      # Запуск TaskIQ worker
    python scripts/run.py scheduler   # Запуск TaskIQ scheduler
    python scripts/run.py rag-worker     # Запуск RAG worker

Конфигурация загружается из conf.json и conf.local.json.
Переменные окружения имеют приоритет над конфигами.
"""
import sys
import subprocess
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Конфигурация сервисов
SERVICES = {
    # FastAPI сервисы (uvicorn)
    "agents": {
        "type": "uvicorn",
        "app": "apps.agents.main:app",
        "port": "8001",
    },
    "frontend": {
        "type": "uvicorn",
        "app": "apps.frontend.main:app",
        "port": "8002",
    },
    "crm": {
        "type": "uvicorn",
        "app": "apps.crm.main:app",
        "port": "8003",
    },
    "rag": {
        "type": "uvicorn",
        "app": "apps.rag.main:app",
        "port": "8004",
    },
    
    # TaskIQ workers
    "worker": {
        "type": "taskiq-worker",
        "broker": "apps.broker.worker:broker",
        "workers": "1",
    },
    "rag-worker": {
        "type": "taskiq-worker",
        "broker": "apps.rag_worker.worker:broker",
        "workers": "1",
    },
    
    # TaskIQ scheduler
    "scheduler": {
        "type": "taskiq-scheduler",
        "scheduler": "apps.scheduler.scheduler:scheduler",
    },
}


def main():
    if len(sys.argv) < 2:
        print("Использование: python scripts/run.py <service>")
        print(f"Доступные сервисы: {', '.join(SERVICES.keys())}")
        sys.exit(1)
    
    service = sys.argv[1]
    
    if service not in SERVICES:
        print(f"Неизвестный сервис: {service}")
        print(f"Доступные: {', '.join(SERVICES.keys())}")
        sys.exit(1)
    
    config = SERVICES[service]
    service_type = config["type"]
    
    if service_type == "uvicorn":
        cmd = [
            sys.executable, "-u", "-m", "uvicorn",
            config["app"],
            "--host", "0.0.0.0",
            "--port", config["port"],
            "--reload",
            "--access-log"
        ]
    elif service_type == "taskiq-worker":
        cmd = [
            sys.executable, "-u", "-m", "taskiq",
            "worker",
            config["broker"],
            "--workers", config["workers"]
        ]
    elif service_type == "taskiq-scheduler":
        cmd = [
            sys.executable, "-u", "-m", "taskiq",
            "scheduler",
            config["scheduler"]
        ]
    else:
        print(f"Неизвестный тип сервиса: {service_type}")
        sys.exit(1)
    
    print(f"Запуск {service}: {' '.join(cmd)}")
    subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    main()
