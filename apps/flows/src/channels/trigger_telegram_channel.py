"""
Канал исполнения для входящих Telegram-триггеров.

Тот же runtime и Redis emitter, что у A2A; имя канала отличается для трейсинга и метрик.
"""

from apps.flows.src.channels.a2a import A2AChannel


class TelegramInboundChannel(A2AChannel):
    name = "telegram"
