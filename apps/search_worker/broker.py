"""TaskIQ broker для search worker (очередь ``search``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="search", service_name="search_worker")

__all__ = ["broker"]
