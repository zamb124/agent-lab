"""
Platform flows worker package.
"""

# Не импортируем здесь worker app - это вызывает циклический импорт.
# Producers/tasks import broker primitives from apps.flows_worker.broker_core.

__all__ = []
