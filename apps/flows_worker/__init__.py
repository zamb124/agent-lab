""""
Пакет platform flows worker.
"""

# Не импортируем здесь worker app — это вызывает циклический импорт.
# Producers/tasks импортируют примитивы broker из apps.flows_worker.broker_core.

__all__ = []
