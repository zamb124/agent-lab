"""
Точка входа для RAG Worker.

Запуск: taskiq worker apps.rag_worker.worker:broker
"""

# Инициализируем settings
from apps.rag_worker.config import get_settings
get_settings()

# Импортируем broker из core
from apps.broker.broker import broker

# Регистрируем startup/shutdown события
import apps.rag_worker.worker  # noqa: F401

# Экспортируем объекты для taskiq CLI
__all__ = ["broker"]
