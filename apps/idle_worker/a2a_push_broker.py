"""TaskIQ broker для доставки A2A push (очередь ``a2a_push``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="a2a_push", service_name="a2a_push_worker")

__all__ = ["broker"]
