"""
Конфигурация для frontend CRM тестов.

Тесты API CRM требуют запущенный CRM сервер.
Используем crm_server_process из основного conftest.py.
"""

import pytest
import pytest_asyncio
import os


@pytest.fixture(autouse=True)
def setup_crm_service_url(crm_server_process):
    """
    Автоматически устанавливает URL CRM сервиса для всех тестов.
    
    Зависит от crm_server_process - CRM сервер будет запущен 
    перед выполнением тестов в этом модуле.
    """
    os.environ["TEST_CRM_SERVICE_URL"] = crm_server_process["url"]
    yield
    os.environ.pop("TEST_CRM_SERVICE_URL", None)


@pytest_asyncio.fixture
async def crm_api_client(frontend_client, setup_crm_service_url):
    """
    Frontend client с настроенным CRM сервисом.
    
    Использует frontend_client + гарантирует что CRM доступен.
    """
    return frontend_client

