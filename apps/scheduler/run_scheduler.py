"""
Скрипт для запуска TaskIQ scheduler.
Используется для дебага в PyCharm.

В PyCharm создайте конфигурацию запуска:
- Script path: apps/scheduler/run_scheduler.py
- Python interpreter: выберите ваш .venv
- Working directory: корень проекта
"""

import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Импортируем scheduler для регистрации tasks
import apps.scheduler.scheduler  # noqa: E402, F401

if __name__ == "__main__":
    original_argv = sys.argv.copy()

    sys.argv = ["taskiq", "scheduler", "apps.scheduler.scheduler:scheduler"]

    try:
        import runpy
        runpy.run_module("taskiq", run_name="__main__", alter_sys=True)
    finally:
        sys.argv = original_argv

