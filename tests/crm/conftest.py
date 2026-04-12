"""
CRM-специфичные фикстуры.

Основные фикстуры в tests/fixtures/:
- crm_client (ASGI transport) — после старта вызывает ensure namespace/типов
  (tests.fixtures.crm_test_setup.ensure_crm_per_test_namespace_and_types).
- crm_service (реальный HTTP)
- crm_client_http (HTTP к реальному сервису)

Здесь: прямой доступ к контейнеру CRM при необходимости.
"""

import pytest


@pytest.fixture
def crm_container():
    """
    CRM Container для прямого доступа к сервисам.

    Для E2E используй crm_client.
    """
    from apps.crm.container import get_crm_container

    return get_crm_container()
