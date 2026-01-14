"""
TaskIQ tasks infrastructure.

Содержит session_lock middleware и фабрики для создания brokers.

ВАЖНО: broker и scheduler импортируются напрямую из apps.broker.broker,
НЕ из core.tasks (чтобы избежать circular import).
"""

from core.tasks.session_lock import session_lock_middleware, SessionLockMiddleware


__all__ = [
    "session_lock_middleware",
    "SessionLockMiddleware",
]
