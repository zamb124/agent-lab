"""
Фикстуры для тестов платформы.

Структура:
- workers.py: readiness-фикстуры TaskIQ-воркеров стека + taskiq_scheduler
- services.py: readiness-фикстуры HTTP-сервисов стека (granian, make test-up)
- clients.py: HTTP клиенты для тестирования API (ASGI и HTTP)
- auth.py: Фикстуры для авторизации (4 типа пользователей)
- e2e_scope.py: статический test scope для -n0 E2E-фаз

Использование в tests/conftest.py:
    pytest_plugins = ["tests.fixtures.services", "tests.fixtures.clients", "tests.fixtures.workers", "tests.fixtures.auth"]
"""
