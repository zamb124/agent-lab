"""
CRM-специфичные фикстуры.

Основные фикстуры в tests/fixtures/:
- crm_client (ASGI transport) — после старта вызывает ensure namespace/типов
  (tests.fixtures.crm_test_setup.ensure_crm_per_test_namespace_and_types).
- crm_service (реальный HTTP)
- crm_client_http (HTTP к реальному сервису)

Здесь: прямой доступ к контейнеру CRM при необходимости.
OpenFGA обязателен для CRM PDP (нет SQL fallback).
"""

from collections.abc import Iterator

import pytest

from core.config.models import OpenFGAConfig


@pytest.fixture(autouse=True)
def _crm_requires_openfga(openfga_settings: OpenFGAConfig) -> Iterator[None]:
    """CRM CrmEntityAccessService — только OpenFGA; без test store тесты не гоняются."""
    from apps.crm.container import reset_crm_container

    reset_crm_container()
    _ = openfga_settings
    try:
        yield
    finally:
        reset_crm_container()


@pytest.fixture
def crm_container(openfga_settings: OpenFGAConfig):
    """
    CRM Container для прямого доступа к сервисам.

    Для E2E используй crm_client.
    """
    _ = openfga_settings
    from apps.crm.container import get_crm_container

    return get_crm_container()
