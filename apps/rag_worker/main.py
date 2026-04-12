"""
Точка входа для RAG Worker.

Запуск: taskiq worker apps.rag_worker.worker:broker
"""

import apps.rag_worker.worker  # noqa: F401

from apps.rag_worker.worker import broker

__all__ = ["broker"]
