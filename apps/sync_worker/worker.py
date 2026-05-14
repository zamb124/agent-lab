"""
Точка входа для Sync Worker.

Запуск: taskiq worker apps.sync_worker.worker:worker_app
"""

from apps.sync.config import SyncSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_sync_worker = load_merged_config(service_name="sync_worker", silent=True)
_sync_worker_settings = SyncSettings(**_merged_sync_worker)
setup_worker_logging_early("sync_worker", logging_config=_sync_worker_settings.logging)
set_settings(_sync_worker_settings)

import apps.sync.realtime.notification_tasks  # noqa: F401, E402
import apps.sync.realtime.tasks  # noqa: F401, E402
from apps.sync.realtime.broker import broker as worker_app  # noqa: E402

__all__ = ["worker_app"]
