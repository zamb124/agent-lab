"""RAG worker tasks package.

Импортируй ``task_names`` (declarations) или конкретный ``*_tasks`` module.
Пакетный init не регистрирует ``@platform_task`` — иначе HTTP-producer
(``from apps.rag_worker.tasks.task_names import ...``) падает без брокера.
"""

__all__: list[str] = []
