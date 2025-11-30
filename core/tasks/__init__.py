"""
TaskIQ tasks infrastructure.

Единый брокер для всей системы (Shared DB).
"""

from core.tasks.broker import broker

__all__ = ["broker"]

