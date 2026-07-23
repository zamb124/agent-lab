""""
Пакет platform flows worker.
"""

# Не импортируем здесь worker app — это вызывает циклический импорт.
# Producers ставят задачи через core.tasks.enqueue; broker — из apps.flows_worker.broker.

__all__ = []
