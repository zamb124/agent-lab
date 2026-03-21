"""Реэкспорт единого Sync broker (см. apps.sync.realtime.broker)."""

from apps.sync.realtime.broker import broker, scheduler

__all__ = ["broker", "scheduler"]
