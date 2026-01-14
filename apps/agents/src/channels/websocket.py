"""
WebSocketChannel - канал A2A поверх WebSocket.

Реализует те же интерфейсы и поведение, что и A2AChannel,
но с отдельным именем канала для идентификации в контексте.
"""

from apps.agents.src.channels.a2a import A2AChannel


class WebSocketChannel(A2AChannel):
    """
    WebSocket канал коммуникации.

    Использует общую реализацию A2AChannel для работы с A2A типами
    и Redis streaming.
    """

    name = "websocket"


