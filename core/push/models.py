"""
Модели для Web Push подписок.

PushSubscription перенесена в core.db.models.platform (shared БД).
Реэкспорт для обратной совместимости.
"""

from core.db.models.platform import PushSubscription

__all__ = ["PushSubscription"]
