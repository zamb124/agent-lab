"""
Скрипт для запуска TaskIQ worker.
Используется для дебага в PyCharm.

В PyCharm создайте конфигурацию запуска:
- Script path: apps/broker/run_worker.py
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
     - Parameters: worker apps.broker.worker:broker -w 1
   - Или используйте `pydevd.settrace()` в коде для принудительной привязки дебаггера

3. Worker запускается с флагом `-w 1` (один worker) для упрощения дебага
"""

import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Импортируем worker для регистрации tasks и startup/shutdown событий
import apps.broker.worker  # noqa: E402, F401

# Запускаем worker через CLI taskiq
if __name__ == "__main__":
    # Для дебага в PyCharm: принудительная привязка дебаггера
    # Раскомментируйте следующие строки, если точки остановки не работают:
    # import pydevd
    # pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True)
    
    # Сохраняем оригинальные аргументы
    original_argv = sys.argv.copy()
    
    # Устанавливаем аргументы для taskiq CLI
    # -w 1 - один worker процесс для дебага
    sys.argv = ["taskiq", "worker", "apps.broker.worker:broker", "-w", "1"]
    
    try:
        # Запускаем taskiq как модуль
        # Это позволяет PyCharm правильно привязать точки остановки
        import runpy
        runpy.run_module("taskiq", run_name="__main__", alter_sys=True)
    finally:
        # Восстанавливаем оригинальные аргументы
        sys.argv = original_argv

