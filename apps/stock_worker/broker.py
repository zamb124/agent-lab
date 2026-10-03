"""TaskIQ broker для stock worker (очередь ``stock``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="stock", service_name="stock_worker")

__all__ = ["broker"]
