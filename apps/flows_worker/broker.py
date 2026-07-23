"""TaskIQ broker для flows worker (очередь ``flows_worker``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="flows_worker", service_name="flows_worker")

__all__ = ["broker"]
