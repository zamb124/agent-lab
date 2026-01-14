"""
CRM-специфичные фикстуры.

Основные фикстуры теперь в tests/fixtures/:
- crm_client (ASGI transport) - из tests/fixtures/clients.py
- crm_service (реальный HTTP) - из tests/fixtures/services.py
- crm_client_http (HTTP к реальному сервису) - из tests/fixtures/clients.py

Здесь остаются только CRM-специфичные утилиты.
"""

import pytest


@pytest.fixture
def crm_container():
    """
    CRM Container для прямого доступа к сервисам.
    
    Используется ТОЛЬКО если нужен прямой доступ к репозиториям/сервисам.
    Для E2E тестов используй crm_client!
    """
    from apps.crm.container import get_crm_container
    return get_crm_container()

