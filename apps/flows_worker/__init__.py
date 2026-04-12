"""
Platform flows worker package.
"""

# Не импортируем здесь worker app - это вызывает циклический импорт.
# Импорт должен быть напрямую: from apps.flows_worker.broker import broker

__all__ = []
