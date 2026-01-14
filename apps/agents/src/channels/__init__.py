"""
Каналы коммуникации с агентами.

BaseChannel - абстрактный интерфейс канала.
A2AChannel - реализация A2A протокола.
"""

from apps.agents.src.channels.base import BaseChannel, PermissionDenied
from apps.agents.src.channels.types import PreparedTaskParams
from apps.agents.src.channels.factory import get_channel

__all__ = ["BaseChannel", "PermissionDenied", "PreparedTaskParams", "get_channel"]

