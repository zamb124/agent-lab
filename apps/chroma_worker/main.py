"""
Точка входа для ChromaWorker.

Запуск: taskiq worker apps.chroma_worker.worker:broker
"""

# Инициализируем settings
from apps.chroma_worker.config import get_settings
get_settings()

# Импортируем broker из core
from apps.broker.broker import broker

# Регистрируем startup/shutdown события
import apps.chroma_worker.worker  # noqa: F401

# Экспортируем объекты для taskiq CLI
__all__ = ["broker"]

