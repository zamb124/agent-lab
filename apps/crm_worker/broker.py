"""TaskIQ broker для CRM worker (очередь ``crm``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="crm", service_name="crm_worker")

__all__ = ["broker"]
