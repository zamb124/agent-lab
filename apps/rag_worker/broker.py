"""TaskIQ broker для RAG worker (очередь ``rag``)."""

from core.tasks.broker import create_broker

broker = create_broker(queue_name="rag", service_name="rag_worker")

__all__ = ["broker"]
