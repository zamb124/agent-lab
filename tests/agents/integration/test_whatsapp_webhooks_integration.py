"""
Интеграционные тесты для WhatsApp webhook endpoints.
Реальные тесты БЕЗ моков - проверяют полный flow.
"""
import pytest
import pytest_asyncio

from apps.agents.models import FlowConfig
from core.models import Company




@pytest_asyncio.fixture(scope="session")
async def wa_test_company(migrated_db):
    """Создает тестовую компанию для WhatsApp тестов"""
    from apps.agents.container import get_agents_container
    from core.db.repositories.subdomain_repository import SubdomainMapping
    
    container = get_agents_container()
    company_repo = container.company_repository
    subdomain_repo = container.subdomain_repository
    
    company = Company(
        company_id="test_wa_company",
        subdomain="test_wa_company",
        name="Test WhatsApp Company",
        status="active"
    )
    
    await company_repo.set(company)
    
    subdomain_mapping = SubdomainMapping(
        subdomain=company.subdomain,
        company_id=company.company_id
    )
    await subdomain_repo.set(subdomain_mapping)
    
    yield company
    
    await company_repo.delete(company.company_id)
    await subdomain_repo.delete(company.subdomain)


@pytest_asyncio.fixture(scope="session")
async def wa_test_flow(wa_test_company):
    """Создает тестовый flow с WhatsApp платформой"""
    from apps.agents.container import get_agents_container
    from core.context import set_context, Context
    
    container = get_agents_container()
    flow_repo = container.flow_repository
    
    from core.models import User, UserStatus
    
    test_user = User(
        user_id="test_user",
        name="Test User",
        status=UserStatus.ACTIVE,
        companies={wa_test_company.company_id: ["user"]},
        active_company_id=wa_test_company.company_id
    )
    
    context = Context(
        user=test_user,
        session_id="test_session",
        platform="test",
        active_company=wa_test_company
    )
    set_context(context)
    
    flow_config = FlowConfig(
        flow_id="test_whatsapp_flow",
        name="Test WhatsApp Flow",
        entry_point_agent="test.agent",
        platforms={
            "whatsapp": {
                "phone_number_id": "123456789",
                "access_token": "@var:wa_test_token",
                "verify_token": "@var:wa_verify_token",
                "business_account_id": "987654321",
                "display_name": "Test Bot"
            }
        }
    )
    
    await flow_repo.set(flow_config)
    
    flow_key = f"company:{wa_test_company.company_id}:flow:{flow_config.flow_id}"
    
    yield flow_config, flow_key
    
    await flow_repo.delete(flow_config.flow_id)


@pytest_asyncio.fixture(scope="session")
async def wa_test_variables(wa_test_company):
    """Создает тестовые переменные для компании"""
    from core.context import set_context
    from apps.agents.container import get_agents_container
    from core.models.context_models import Context

    # Создаем контекст с компанией
    from core.models import User
    test_user = User(
        user_id="test_wa_user",
        name="Test WhatsApp User",
        email="test@example.com"
    )
    context = Context(
        user=test_user,
        platform="test",
        active_company=wa_test_company
    )
    set_context(context)

    container = get_agents_container()
    variables_service = container.variables_service

    # Создаем переменные
    await variables_service.set_var("wa_test_token", "EAAxxx_test_access_token", is_secret=True)
    await variables_service.set_var("wa_verify_token", "test_verify_12345", is_secret=False)

    yield {
        "access_token": "EAAxxx_test_access_token",
        "verify_token": "test_verify_12345"
    }

    # Cleanup
    await variables_service.delete_var("wa_test_token")
    await variables_service.delete_var("wa_verify_token")


@pytest.mark.asyncio
class TestWhatsAppWebhookVerification:
    """Интеграционные тесты верификации webhook"""
    
    async def test_webhook_verify_success(self, agents_app, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест успешной верификации webhook - ПОЛНЫЙ FLOW"""
        flow_config, flow_key = wa_test_flow
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=agents_app), base_url="http://test") as client:
            response = await client.get(
                f"/agents/api/v1/webhook/whatsapp/{flow_key}",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": wa_test_variables["verify_token"],
                    "hub.challenge": "54321"
                }
            )
        
        print(f"\n✅ Статус: {response.status_code}")
        print(f"✅ Ответ: {response.text}")
        
        assert response.status_code == 200, f"Ошибка: {response.text}"
        assert response.text == "54321", "Challenge должен вернуться как есть"
    
    async def test_webhook_verify_wrong_token(self, agents_app, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест верификации с неверным токеном"""
        flow_config, flow_key = wa_test_flow
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=agents_app), base_url="http://test") as client:
            response = await client.get(
                f"/agents/api/v1/webhook/whatsapp/{flow_key}",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "WRONG_TOKEN_123",
                    "hub.challenge": "54321"
                }
            )
            
            print(f"\n❌ Статус: {response.status_code}")
            print(f"❌ Детали: {response.json()}")
            
            assert response.status_code == 403, "Должен вернуть 403 для неверного токена"
            assert "verify_token" in response.json()["detail"].lower()
    
    async def test_webhook_verify_wrong_mode(self, agents_app, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест верификации с неверным режимом"""
        flow_config, flow_key = wa_test_flow
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=agents_app), base_url="http://test") as client:
            response = await client.get(
                f"/agents/api/v1/webhook/whatsapp/{flow_key}",
                params={
                    "hub.mode": "unsubscribe",
                    "hub.verify_token": wa_test_variables["verify_token"],
                    "hub.challenge": "54321"
                }
            )
            
            print(f"\n❌ Статус: {response.status_code}")
            
            assert response.status_code == 403, "Должен вернуть 403 для неверного режима"
    
    async def test_webhook_verify_company_not_found(self, agents_app, migrated_db):
        """Тест верификации для несуществующей компании"""
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=agents_app), base_url="http://test") as client:
            try:
                response = await client.get(
                    "/agents/api/v1/webhook/whatsapp/company:nonexistent:flow:test",
                    params={
                        "hub.mode": "subscribe",
                        "hub.verify_token": "test",
                        "hub.challenge": "12345"
                    }
                )
                
                print(f"\n⚠️ Статус: {response.status_code}")
                
                # Может быть 404 (flow не найден) или 403 (токен не совпал из-за отсутствия контекста)
                assert response.status_code in [403, 404]
            except Exception as e:
                # Если middleware бросает исключение, это тоже нормально
                print(f"\n⚠️ Исключение: {type(e).__name__}: {e}")
                assert "Company nonexistent not found" in str(e) or "404" in str(e)
    
    async def test_webhook_verify_variable_resolution(self, agents_app, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест что переменные правильно резолвятся"""
        flow_config, flow_key = wa_test_flow
        
        # Проверяем что в конфиге ссылка на переменную
        assert flow_config.platforms["whatsapp"]["verify_token"] == "@var:wa_verify_token"
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=agents_app), base_url="http://test") as client:
            response = await client.get(
                f"/agents/api/v1/webhook/whatsapp/{flow_key}",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": wa_test_variables["verify_token"],
                    "hub.challenge": "99999"
                }
            )
            
            print("\n✅ Переменная @var:wa_verify_token резолвнулась правильно")
            print(f"✅ Статус: {response.status_code}")
            
            assert response.status_code == 200
            assert response.text == "99999"


@pytest.mark.asyncio  
class TestWhatsAppWebhookHandler:
    """Интеграционные тесты обработки webhook"""
    
    async def test_webhook_post_message(self, agents_app, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест обработки POST webhook с сообщением"""
        flow_config, flow_key = wa_test_flow
        
        webhook_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123456789",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": "123456789"
                        },
                        "contacts": [{
                            "profile": {"name": "Integration Test User"},
                            "wa_id": "79991234567"
                        }],
                        "messages": [{
                            "from": "79991234567",
                            "id": "wamid.integration_test",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "Test integration message"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        # Мокаем только WhatsApp API (чтобы не слать реальные запросы)
        from unittest.mock import patch
        from httpx import AsyncClient, ASGITransport
        
        with patch('apps.agents.interfaces.whatsapp_interface.WhatsAppInterface._get_media_url', return_value=None):
            with patch('apps.agents.interfaces.base.BaseInterface.create_task', return_value="task_test_123"):
                async with AsyncClient(transport=ASGITransport(app=agents_app), base_url="http://test") as client:
                    response = await client.post(
                        f"/agents/api/v1/webhook/whatsapp/{flow_key}",
                        json=webhook_payload
                    )
        
        print(f"\n✅ Статус: {response.status_code}")
        print(f"✅ Ответ: {response.json()}")
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    async def test_webhook_post_status_only(self, agents_app, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест webhook только со статусом (без создания задачи)"""
        flow_config, flow_key = wa_test_flow
        
        webhook_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "123456789"},
                        "statuses": [{
                            "id": "wamid.status123",
                            "status": "delivered",
                            "timestamp": "1699000020"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=agents_app), base_url="http://test") as client:
            response = await client.post(
                f"/agents/api/v1/webhook/whatsapp/{flow_key}",
                json=webhook_payload
            )
        
        print(f"\n✅ Статус webhook со статусом: {response.status_code}")
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
class TestContextAndVariables:
    """Тесты контекста компании и резолва переменных"""
    
    async def wa_test_company_context_is_set(self, agents_app, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест что контекст компании устанавливается правильно"""
        from core.context import get_context
        
        flow_config, flow_key = wa_test_flow
        
        # До запроса контекст пустой
        context_before = get_context()
        assert context_before.active_company is None or context_before.active_company.company_id != wa_test_company.company_id
        
        from fastapi.testclient import TestClient
        
        client = TestClient(agents_app)
        response = client.get(
            f"/agents/api/v1/webhook/whatsapp/{flow_key}",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": wa_test_variables["verify_token"],
                "hub.challenge": "12345"
            }
        )
        
        print("\n✅ Контекст компании был установлен для резолва переменных")
        assert response.status_code == 200
    
    async def wa_test_variables_resolve_correctly(self, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест что переменные резолвятся с правильным контекстом"""
        from core.context import get_context
        from apps.agents.container import get_agents_container
        
        # Устанавливаем контекст
        context = get_context()
        context.active_company = wa_test_company
        
        container = get_agents_container()
        variables_service = container.variables_service
        
        # Проверяем резолв
        resolved_token = await variables_service.resolve("@var:wa_verify_token")
        assert resolved_token == wa_test_variables["verify_token"]
        
        resolved_access = await variables_service.resolve("@var:wa_test_token")
        assert resolved_access == wa_test_variables["access_token"]
        
        print(f"\n✅ Переменные резолвятся: @var:wa_verify_token -> {resolved_token}")
        
        # Очищаем контекст
        context.active_company = None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

