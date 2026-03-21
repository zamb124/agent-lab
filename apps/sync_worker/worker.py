"""
Точка входа для Sync Worker.

Запуск: taskiq worker apps.sync_worker.worker:broker
"""

from apps.sync_worker.config import get_settings
get_settings()

from apps.sync.realtime.broker import broker

import apps.sync.realtime.tasks  # noqa: F401

__all__ = ["broker"]
