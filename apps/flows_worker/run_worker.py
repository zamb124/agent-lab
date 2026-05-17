"""
Скрипт для запуска TaskIQ flows worker.
Используется для дебага в PyCharm.

В PyCharm создайте конфигурацию запуска:
- Script path: apps/flows_worker/run_worker.py
- Python interpreter: выберите ваш .venv
- Working directory: корень проекта

ВАЖНО: Для работы точек остановки (breakpoints) в worker процессах:

1. В настройках PyCharm включите дебаг для multiprocessing:
   - Settings → Build, Execution, Deployment → Python Debugger
   - Включите "Attach to subprocess automatically"
   - Или используйте "Gevent compatible" если используется gevent

2. Если точки остановки все еще не работают:
   - Попробуйте конфигурацию "Python module":
     - Module name: taskiq
     - Parameters: worker apps.flows_worker.worker:worker_app -w 1
   - Или используйте `pydevd.settrace()` в коде для принудительной привязки дебаггера

3. Worker запускается с флагом `-w 1` (один worker) для упрощения дебага
"""

import runpy
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import apps.flows_worker.worker as _flows_worker_module  # noqa: E402

_WORKER_MODULE = _flows_worker_module

if __name__ == "__main__":
    # Для дебага в PyCharm: принудительная привязка дебаггера
    # Раскомментируйте следующие строки, если точки остановки не работают:
    # import pydevd
    # pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True)

    original_argv = sys.argv.copy()
    sys.argv = ["taskiq", "worker", "apps.flows_worker.worker:worker_app", "-w", "1"]

    try:
        runpy.run_module("taskiq", run_name="__main__", alter_sys=True)
    finally:
        sys.argv = original_argv
