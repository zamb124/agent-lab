"""TaskIQ broker для Sync realtime команд (очередь ``sync``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="sync", service_name="sync_worker")

__all__ = ["broker"]
