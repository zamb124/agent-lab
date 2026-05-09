"""Платформенные константы RAG (in-process pgvector на контейнере).

Должно совпадать с провайдером в ``BaseContainer.rag_repository``
(``get_rag_provider(RAG_IN_PROCESS_PROVIDER_ID)``).
"""

RAG_IN_PROCESS_PROVIDER_ID = "pgvector"
