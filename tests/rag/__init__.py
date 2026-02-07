"""
Интеграционные тесты RAG Service.

Принципы:
- Без моков (кроме LLM)
- Реальный PostgreSQL + pgvector
- Реальный MinIO (порт 9002)
- Фикстуры централизованы в tests/conftest.py
"""


