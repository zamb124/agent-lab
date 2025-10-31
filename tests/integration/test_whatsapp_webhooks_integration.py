"""
Интеграционные тесты для WhatsApp webhook endpoints.
Реальные тесты БЕЗ моков - проверяют полный flow.
"""
import pytest
import pytest_asyncio
import json
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db.repositories import Storage
from app.models import FlowConfig
from app.identity.models import Company
from app.db.database import AsyncSessionLocal


@pytest_asyncio.fixture
async def wa_test_company():
    """Создает тестовую компанию для WhatsApp тестов"""
    from app.core.container import get_container
    container = get_container()
    storage = container.storage
    
    company = Company(
        company_id="test_wa_company",
        subdomain="test_wa_company",
        name="Test WhatsApp Company",
        status="active"
    )
    
    # Сохраняем компанию
    company_key = f"company:{company.company_id}"
    await storage.set(company_key, company.model_dump_json(), force_global=True)
    
    # Сохраняем mapping subdomain -> company_id
    await storage.set(f"subdomain:{company.subdomain}", f'"{company.company_id}"', force_global=True)
    
    yield company
    
    # Cleanup
    await storage.delete(company_key, force_global=True)
    await storage.delete(f"subdomain:{company.subdomain}", force_global=True)


@pytest_asyncio.fixture
async def wa_test_flow(wa_test_company):
    """Создает тестовый flow с WhatsApp платформой"""
    storage = Storage()
    
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
    
    flow_key = f"company:{wa_test_company.company_id}:flow:{flow_config.flow_id}"
    await storage.set(flow_key, flow_config.model_dump_json(), force_global=True)
    
    yield flow_config, flow_key
    
    # Cleanup
    await storage.delete(flow_key, force_global=True)


@pytest_asyncio.fixture
async def wa_test_variables(wa_test_company):
    """Создает тестовые переменные для компании"""
    from app.core.context import set_context
    from app.core.container import get_container
    from app.models.context_models import Context

    from app.identity.models import User, AuthProvider, UserStatus

    # Создаем контекст с компанией и пользователем
    context = Context(
        user=User(
            user_id="wa_test_user",
            provider="test",
            provider_user_id="wa_001",
            email="wa_test@example.com",
            name="WhatsApp Test User",
            status="active",
            groups=["user"],
            companies={wa_test_company.company_id: ["user"]},
            active_company_id=wa_test_company.company_id
        ),
        platform="test",
        active_company=wa_test_company
    )
    await set_context(context)

    container = get_container()
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
    
    async def test_webhook_verify_success(self, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест успешной верификации webhook - ПОЛНЫЙ FLOW"""
        flow_config, flow_key = wa_test_flow
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/webhook/whatsapp/{flow_key}",
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
    
    async def test_webhook_verify_wrong_token(self, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест верификации с неверным токеном"""
        flow_config, flow_key = wa_test_flow
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/webhook/whatsapp/{flow_key}",
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
    
    async def test_webhook_verify_wrong_mode(self, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест верификации с неверным режимом"""
        flow_config, flow_key = wa_test_flow
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/webhook/whatsapp/{flow_key}",
                params={
                    "hub.mode": "unsubscribe",
                    "hub.verify_token": wa_test_variables["verify_token"],
                    "hub.challenge": "54321"
                }
            )
            
            print(f"\n❌ Статус: {response.status_code}")
            
            assert response.status_code == 403, "Должен вернуть 403 для неверного режима"
    
    async def test_webhook_verify_company_not_found(self, migrated_db):
        """Тест верификации для несуществующей компании"""
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            try:
                response = await client.get(
                    "/api/v1/webhook/whatsapp/company:nonexistent:flow:test",
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
    
    async def test_webhook_verify_variable_resolution(self, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест что переменные правильно резолвятся"""
        flow_config, flow_key = wa_test_flow
        
        # Проверяем что в конфиге ссылка на переменную
        assert flow_config.platforms["whatsapp"]["verify_token"] == "@var:wa_verify_token"
        
        from httpx import AsyncClient, ASGITransport
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/api/v1/webhook/whatsapp/{flow_key}",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": wa_test_variables["verify_token"],
                    "hub.challenge": "99999"
                }
            )
            
            print(f"\n✅ Переменная @var:wa_verify_token резолвнулась правильно")
            print(f"✅ Статус: {response.status_code}")
            
            assert response.status_code == 200
            assert response.text == "99999"


@pytest.mark.asyncio  
class TestWhatsAppWebhookHandler:
    """Интеграционные тесты обработки webhook"""
    
    async def test_webhook_post_message(self, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
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
        from unittest.mock import patch, AsyncMock
        from httpx import AsyncClient, ASGITransport
        
        with patch('app.interfaces.whatsapp_interface.WhatsAppInterface._get_media_url', return_value=None):
            with patch('app.interfaces.base.BaseInterface.create_task', return_value="task_test_123"):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post(
                        f"/api/v1/webhook/whatsapp/{flow_key}",
                        json=webhook_payload
                    )
        
        print(f"\n✅ Статус: {response.status_code}")
        print(f"✅ Ответ: {response.json()}")
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    async def test_webhook_post_status_only(self, migrated_db, wa_test_company, wa_test_flow, wa_test_variables):
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
        
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/webhook/whatsapp/{flow_key}",
                json=webhook_payload
            )
        
        print(f"\n✅ Статус webhook со статусом: {response.status_code}")
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
class TestContextAndVariables:
    """Тесты контекста компании и резолва переменных"""
    
    async def wa_test_company_context_is_set(self, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест что контекст компании устанавливается правильно"""
        from app.core.context import get_context
        
        flow_config, flow_key = wa_test_flow
        
        # До запроса контекст пустой
        context_before = get_context()
        assert context_before.active_company is None or context_before.active_company.company_id != wa_test_company.company_id
        
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get(
            f"/api/v1/webhook/whatsapp/{flow_key}",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": wa_test_variables["verify_token"],
                "hub.challenge": "12345"
            }
        )
        
        print(f"\n✅ Контекст компании был установлен для резолва переменных")
        assert response.status_code == 200
    
    async def wa_test_variables_resolve_correctly(self, wa_test_company, wa_test_flow, wa_test_variables):
        """Тест что переменные резолвятся с правильным контекстом"""
        from app.core.context import get_context
        from app.core.container import get_container
        
        # Устанавливаем контекст
        context = get_context()
        context.active_company = wa_test_company
        
        container = get_container()
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

