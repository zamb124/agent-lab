"""
Фикстуры для тестов платформы.

Структура:
- workers.py: SessionWorkerManager, SessionServerManager для worker'ов и серверов
- services.py: Фикстуры для запуска сервисов (agents, rag, crm, frontend)
- clients.py: HTTP клиенты для тестирования API (ASGI и HTTP)
- auth.py: Фикстуры для авторизации (4 типа пользователей)
- playwright.py: Фикстуры для E2E UI тестов с Playwright

Использование в tests/conftest.py:
    pytest_plugins = ["tests.fixtures.services", "tests.fixtures.clients", "tests.fixtures.workers", "tests.fixtures.auth", "tests.fixtures.playwright"]
"""

# Экспортируем основные классы
from tests.fixtures.workers import SessionWorkerManager, SessionServerManager

__all__ = [
    "SessionWorkerManager",
    "SessionServerManager",
]
