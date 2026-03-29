"""
Точки входа локального runtime (make app).

Нужны отдельные import-path сигнатуры, чтобы тестовые cleanup-паттерны
не пересекались с процессами локального dev-запуска.
"""

from apps.broker.worker import broker as flows_taskiq_broker
from apps.crm.main import app as crm_app
from apps.crm_worker.worker import broker as crm_taskiq_broker
from apps.flows.main import app as flows_app
from apps.frontend.main import app as frontend_app
from apps.rag.main import app as rag_app
from apps.rag_worker.worker import broker as rag_taskiq_broker
from apps.scheduler.main import app as scheduler_app
from apps.scheduler.scheduler import scheduler as platform_scheduler
from apps.sync.main import app as sync_app
from apps.sync_worker.worker import broker as sync_taskiq_broker

