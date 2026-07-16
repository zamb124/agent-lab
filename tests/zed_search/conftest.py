"""
Изолированные тесты zed-search (claude-context MCP).

Эти тесты НЕ требуют PostgreSQL/Redis/TaskIQ — только Ollama + Milvus + npx.
Вынесены в отдельную директорию, чтобы tests/conftest.py (с БД-фикстурами)
не применялся.

Запуск: pytest tests/zed_search/test_zed_search.py -v
"""
