"""
Точки входа локального runtime (make app).

Нужны отдельные import-path сигнатуры, чтобы тестовые cleanup-паттерны
не пересекались с процессами локального dev-запуска.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name == "flows_app":
        from apps.flows.main import app
        return app
    if name == "frontend_app":
        from apps.frontend.main import app
        return app
    if name == "crm_app":
        from apps.crm.main import app
        return app
    if name == "rag_app":
        from apps.rag.main import app
        return app
    if name == "sync_app":
        from apps.sync.main import app
        return app
    if name == "office_app":
        from apps.office.main import app
        return app
    if name == "scheduler_app":
        from apps.scheduler.main import app
        return app
    if name == "flows_taskiq_worker_app":
        from apps.flows_worker.worker import worker_app
        return worker_app
    if name == "rag_taskiq_worker_app":
        from apps.rag_worker.worker import worker_app
        return worker_app
    if name == "sync_taskiq_worker_app":
        from apps.sync_worker.worker import worker_app
        return worker_app
    if name == "crm_taskiq_worker_app":
        from apps.crm_worker.worker import worker_app
        return worker_app
    if name == "idle_taskiq_worker_app":
        from apps.idle_worker.worker import worker_app
        return worker_app
    if name == "platform_scheduler":
        from apps.scheduler.scheduler import scheduler
        return scheduler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

