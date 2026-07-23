"""TaskIQ broker для idle worker (очередь ``idle``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="idle", service_name="idle_worker")

__all__ = ["broker"]
