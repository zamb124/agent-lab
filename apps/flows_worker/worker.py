"""
Точка входа для TaskIQ flows worker.

Запуск: taskiq worker apps.flows_worker.worker:worker_app

Этот модуль:
1. Инициализирует settings сервисов
2. Импортирует worker app из apps.flows_worker.broker
3. Регистрирует startup/shutdown события
4. Регистрирует tasks всех сервисов
"""

import os
import sys

_forced = False
for _k, _v in (
    ("S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL", "http://localhost:19002"),
    ("S3__BUCKETS__TEST_BUCKET__ENDPOINT_URL", "http://localhost:19002"),
):
    _cur = os.environ.get(_k)
    if _cur is None or _cur == "" or "127.0.0.1:19001" in _cur:
        os.environ[_k] = _v
        _forced = True

if _forced:
    from apps.flows.config import reset_settings
    reset_settings()

from apps.flows.config import FlowSettings, set_settings as set_flow_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_flows = load_merged_config(service_name="flows", silent=True)
_flow_worker_settings = FlowSettings(**_merged_flows)
setup_worker_logging_early("flows_worker", logging_config=_flow_worker_settings.logging)
set_flow_settings(_flow_worker_settings)

from apps.flows_worker.broker import broker as worker_app

import apps.flows.src.tasks.company_init_tasks  # noqa: F401
import apps.flows.src.tasks.eval_task  # noqa: F401
import apps.flows.src.tasks.flow_tasks  # noqa: F401
import apps.flows.src.tasks.llm_tasks  # noqa: F401
import apps.flows.src.tasks.node_tasks  # noqa: F401
import apps.flows.src.tasks.scheduled_tasks  # noqa: F401
import apps.flows.src.tasks.tool_tasks  # noqa: F401

# CRM attachment tasks теперь в rag worker (apps/rag_worker/worker.py)
# import apps.crm.tasks.attachment_tasks  # noqa: F401

__all__ = ["worker_app"]
