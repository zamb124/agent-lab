"""
Точка входа для RAG Worker.

Запуск: taskiq worker apps.rag_worker.worker:worker_app
"""

# Инициализируем settings
from apps.rag_worker.config import get_settings

get_settings()

# Импортируем worker app
# Регистрируем startup/shutdown события
import apps.rag_worker.worker  # noqa: F401, E402
from apps.rag_worker.broker import broker as worker_app  # noqa: E402

# Экспортируем объекты для taskiq CLI
__all__ = ["worker_app"]
