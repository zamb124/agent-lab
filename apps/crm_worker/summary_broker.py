"""TaskIQ broker для CRM daily/period summary (очередь ``crm_summary``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="crm_summary", service_name="crm_summary_worker")

__all__ = ["broker"]
