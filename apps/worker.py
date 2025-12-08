"""
Точка входа для TaskIQ воркера и планировщика приложений.

Связывает ядро (core) и приложения (apps).
Импортирует все модули с задачами для их регистрации в брокере.
"""

from core.tasks.broker import broker, scheduler, schedule_source
from core.logging import setup_logging

# Настраиваем логирование при импорте модуля (до запуска воркера)
setup_logging("worker")

# === Регистрация задач приложений ===
# Импортируем модули, чтобы декораторы @broker.task сработали
import apps.agents.tasks.agent_tasks  # noqa: F401
import apps.agents.tasks.message_tasks  # noqa: F401
import apps.agents.tasks.company_tasks  # noqa: F401
import apps.frontend.tasks.notification_tasks  # noqa: F401
import apps.agents.services.migration.migrator  # noqa: F401 - migrate_company_defaults
import apps.crm.tasks.attachment_tasks  # noqa: F401 - CRM attachments RAG

# Экспортируем объекты для taskiq CLI
__all__ = ["broker", "scheduler", "schedule_source"]
