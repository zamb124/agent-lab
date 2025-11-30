"""
Фикстуры для тестов frontend.

Общие фикстуры для всех тестов в tests/frontend/.
"""

import pytest_asyncio
import httpx
from httpx import ASGITransport

from core.utils.tokens import get_token_service
from core.db.repositories.subdomain_repository import SubdomainMapping


@pytest_asyncio.fixture
async def frontend_client(frontend_app, test_context, test_user, test_company):
    """
    HTTP клиент для тестирования frontend API с авторизацией.
    
    Создает JWT токен и передает его в cookies для авторизации.
    Использует реальное FastAPI приложение через ASGITransport.
    Host заголовок с поддоменом для определения компании.
    
    Сохраняет пользователя, компанию и subdomain через контейнер приложения.
    """
    container = frontend_app.state.container
    
    await container.company_repository.set(test_company)
    
    subdomain_mapping = SubdomainMapping(
        subdomain=test_company.subdomain,
        company_id=test_company.company_id
    )
    await container.subdomain_repository.set(subdomain_mapping)
    
    await container.user_repository.set(test_user)
    
    token_service = get_token_service()
    token = token_service.create_token(
        user_id=test_user.user_id,
        company_id=test_company.company_id,
        session_id="test_session"
    )
    
    subdomain = test_company.subdomain
    
    transport = ASGITransport(app=frontend_app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://{subdomain}.localhost:8002",
        cookies={"auth_token": token},
        headers={"Host": f"{subdomain}.localhost:8002"}
    ) as client:
        yield client
    
    await container.user_repository.delete(test_user.user_id)
    await container.subdomain_repository.delete(test_company.subdomain)
    await container.company_repository.delete(test_company.company_id)

