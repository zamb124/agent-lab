"""
Точка входа для Sync Worker.

Запуск: taskiq worker apps.sync_worker.worker:broker
"""

from core.config import set_settings
from core.config.loader import load_merged_config

from apps.sync.config import SyncSettings

set_settings(SyncSettings(**load_merged_config(service_name="sync")))

from apps.sync.realtime.broker import broker

import apps.sync.realtime.tasks  # noqa: F401
import apps.sync.realtime.notification_tasks  # noqa: F401

__all__ = ["broker"]
