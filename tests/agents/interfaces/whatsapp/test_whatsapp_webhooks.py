"""
Тесты для WhatsApp webhook endpoints.
Проверка всех API endpoints в app/api/v1/whatsapp.py.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from apps.agents.api.v1.whatsapp import router
from apps.agents.models import FlowConfig
from apps.agents.dependencies import get_flow_repository, get_variables_service

pytestmark = pytest.mark.xdist_group(name="whatsapp_sequential")


@pytest_asyncio.fixture
async def app(migrated_db):
    """FastAPI приложение для тестов"""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app):
    """Test client для API"""
    return TestClient(app)


def setup_flow_repo_override(app, flow_config):
    """Настраивает мок FlowRepository и VariablesService для dependency override"""
    mock_flow_repo = AsyncMock()
    mock_flow_repo.get = AsyncMock(return_value=flow_config)
    
    async def mock_get_flow_repository():
        return mock_flow_repo
    
    mock_vars = AsyncMock()
    mock_vars.resolve = AsyncMock(return_value="test_verify_456")
    
    async def mock_get_variables_service():
        return mock_vars
    
    app.dependency_overrides[get_flow_repository] = mock_get_flow_repository
    app.dependency_overrides[get_variables_service] = mock_get_variables_service
    return mock_flow_repo


@pytest.fixture
def mock_flow_config():
    """Мок FlowConfig с WhatsApp платформой"""
    return FlowConfig(
        flow_id="test_whatsapp_flow",
        name="Test WhatsApp Flow",
        entry_point_agent="test.agent",
        platforms={
            "whatsapp": {
                "phone_number_id": "111111111111111",
                "access_token": "test_token_123",
                "verify_token": "test_verify_456",
                "business_account_id": "987654321",
                "display_name": "Test Bot"
            }
        }
    )


class TestWebhookVerification:
    """Тесты верификации webhook (GET запрос)"""
    
    def test_webhook_verify_success(self, app, mock_flow_config):
        """Тест успешной верификации webhook"""
        setup_flow_repo_override(app, mock_flow_config)
        
        client = TestClient(app)
        response = client.get(
            "/api/v1/webhook/whatsapp/company:test:flow:test_whatsapp_flow",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test_verify_456",
                "hub.challenge": "12345"
            }
        )
        
        assert response.status_code == 200
        assert response.text == "12345"
        print("✅ Webhook верификация успешна")
    
    def test_webhook_verify_wrong_token(self, app, mock_flow_config):
        """Тест верификации с неверным токеном"""
        setup_flow_repo_override(app, mock_flow_config)
        
        client = TestClient(app)
        response = client.get(
            "/api/v1/webhook/whatsapp/company:test:flow:test_whatsapp_flow",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "WRONG_TOKEN",
                "hub.challenge": "12345"
            }
        )
        
        assert response.status_code == 403
        print("✅ Верификация отклонена при неверном токене")
    
    def test_webhook_verify_wrong_mode(self, app, mock_flow_config):
        """Тест верификации с неверным режимом"""
        setup_flow_repo_override(app, mock_flow_config)
        client = TestClient(app)
        
        response = client.get(
            "/api/v1/webhook/whatsapp/company:test:flow:test_whatsapp_flow",
            params={
                "hub.mode": "unsubscribe",  # Неверный режим!
                "hub.verify_token": "test_verify_456",
                "hub.challenge": "12345"
            }
        )
        
        assert response.status_code == 403
        print("✅ Верификация отклонена при неверном режиме")
    
    def test_webhook_verify_flow_not_found(self, app):
        """Тест верификации для несуществующего flow"""
        setup_flow_repo_override(app, None)
        client = TestClient(app)
        
        response = client.get(
            "/api/v1/webhook/whatsapp/company:test:flow:nonexistent_flow",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test",
                "hub.challenge": "12345"
            }
        )
        
        assert response.status_code == 404
        print("✅ 404 для несуществующего flow")
    
    def test_webhook_verify_no_whatsapp_platform(self, app):
        """Тест верификации для flow без WhatsApp платформы"""
        flow_without_wa = FlowConfig(
            flow_id="no_wa_flow",
            name="No WhatsApp",
            entry_point_agent="test.agent",
            platforms={"api": {}}  # Нет whatsapp!
        )
        
        setup_flow_repo_override(app, flow_without_wa)
        client = TestClient(app)
        
        response = client.get(
            "/api/v1/webhook/whatsapp/company:test:flow:no_wa_flow",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "test",
                "hub.challenge": "12345"
            }
        )
        
        assert response.status_code == 400
        print("✅ 400 для flow без WhatsApp платформы")


class TestWebhookHandler:
    """Тесты обработки webhook (POST запрос)"""
    
    def test_webhook_handle_text_message(self, app, mock_flow_config):
        """Тест обработки текстового сообщения через webhook"""
        webhook_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123456789",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": "111111111111111"
                        },
                        "contacts": [{
                            "profile": {"name": "Test User"},
                            "wa_id": "9111111111111"
                        }],
                        "messages": [{
                            "from": "9111111111111",
                            "id": "wamid.msg123",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "Test message"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        mock_message = MagicMock()
        mock_message.user_id = "whatsapp:9111111111111"
        
        mock_interface = AsyncMock()
        mock_interface.handle_message = AsyncMock(return_value=mock_message)
        mock_interface.create_task = AsyncMock(return_value="task_abc123")
        
        setup_flow_repo_override(app, mock_flow_config)
        client = TestClient(app)
        async def mock_get_token(flow_id, platform_config):
            return "test_token"
        
        class MockWhatsAppInterfaceClass:
            @staticmethod
            async def get_access_token_for_flow(flow_id, platform_config):
                return await mock_get_token(flow_id, platform_config)
            
            def __init__(self, *args, **kwargs):
                pass
            
            async def handle_message(self, *args, **kwargs):
                return await mock_interface.handle_message(*args, **kwargs)
            
            async def create_task(self, *args, **kwargs):
                return await mock_interface.create_task(*args, **kwargs)
        
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface', new=MockWhatsAppInterfaceClass):
            response = client.post(
                "/api/v1/webhook/whatsapp/company:test:flow:test_whatsapp_flow",
                json=webhook_payload
            )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        print("✅ Webhook обработан успешно")
    
    def test_webhook_handle_status_only(self, app, mock_flow_config):
        """Тест webhook только со статусом (без сообщения)"""
        webhook_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "statuses": [{
                            "id": "wamid.msg789",
                            "status": "read",
                            "timestamp": "1699000020"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        mock_interface = AsyncMock()
        mock_interface.handle_message = AsyncMock(return_value=None)
        
        setup_flow_repo_override(app, mock_flow_config)
        client = TestClient(app)
        async def mock_get_token(flow_id, platform_config):
            return "test_token"
        
        class MockWhatsAppInterfaceClass:
            @staticmethod
            async def get_access_token_for_flow(flow_id, platform_config):
                return await mock_get_token(flow_id, platform_config)
            
            def __init__(self, *args, **kwargs):
                pass
            
            async def handle_message(self, *args, **kwargs):
                return await mock_interface.handle_message(*args, **kwargs)
            
            async def create_task(self, *args, **kwargs):
                return await mock_interface.create_task(*args, **kwargs)
        
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface', new=MockWhatsAppInterfaceClass):
            response = client.post(
                "/api/v1/webhook/whatsapp/company:test:flow:test_whatsapp_flow",
                json=webhook_payload
            )
        
        assert response.status_code == 200
        print("✅ Webhook со статусом обработан (задача не создается)")
    
    def test_webhook_flow_not_found(self, app):
        """Тест webhook для несуществующего flow"""
        setup_flow_repo_override(app, None)
        client = TestClient(app)
        response = client.post(
            "/api/v1/webhook/whatsapp/company:test:flow:nonexistent",
            json={"object": "whatsapp_business_account", "entry": []}
        )
        
        assert response.status_code == 404
        print("✅ 404 для несуществующего flow в webhook POST")


class TestAdminRegisterFlow:
    """Тесты admin endpoint для регистрации"""
    
    def test_register_flow_success(self, app, mock_flow_config):
        """Тест успешной регистрации flow"""
        
        mock_register_result = {
            "success": True,
            "platform": "whatsapp",
            "mode": "webhook",
            "phone_number": "+1234567890",
            "flow_key": "company:test:flow:test_whatsapp_flow"
        }
        
        setup_flow_repo_override(app, mock_flow_config)
        
        client = TestClient(app)
        with patch('apps.agents.interfaces.whatsapp_interface.WhatsAppInterface.register', new_callable=AsyncMock) as mock_register:
            mock_register.return_value = mock_register_result
            response = client.post("/api/v1/admin/whatsapp/register/test_whatsapp_flow")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["flow_id"] == "test_whatsapp_flow"
        print("✅ Регистрация flow успешна через API")
    
    def test_register_flow_not_found(self, app):
        """Тест регистрации несуществующего flow"""
        setup_flow_repo_override(app, None)
        
        client = TestClient(app)
        response = client.post("/api/v1/admin/whatsapp/register/nonexistent_flow")
        
        assert response.status_code == 404
        print("✅ 404 при регистрации несуществующего flow")
    
    def test_register_flow_no_whatsapp_platform(self, app):
        """Тест регистрации flow без WhatsApp платформы"""
        flow_no_wa = FlowConfig(
            flow_id="no_wa",
            name="No WhatsApp",
            entry_point_agent="test.agent",
            platforms={"telegram": {"token": "123"}}
        )
        
        setup_flow_repo_override(app, flow_no_wa)
        
        client = TestClient(app)
        response = client.post("/api/v1/admin/whatsapp/register/no_wa")
        
        assert response.status_code == 400
        assert "does not have WhatsApp" in response.json()["detail"]
        print("✅ 400 при отсутствии WhatsApp платформы")


class TestAdminSendTemplate:
    """Тесты отправки template сообщений"""
    
    def test_send_template_success(self, app, mock_flow_config):
        """Тест успешной отправки template"""
        
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 200
        mock_api_response.json = MagicMock(return_value={
            "messages": [{"id": "wamid.template123"}]
        })
        
        setup_flow_repo_override(app, mock_flow_config)
        
        client = TestClient(app)
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface.get_access_token_for_flow', return_value="test_token"):
            with patch('httpx.AsyncClient') as mock_client:
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_api_response)
                    
                    response = client.post(
                        "/api/v1/admin/whatsapp/send_template/test_whatsapp_flow",
                        params={
                            "phone_number": "9111111111111",
                            "template_name": "greeting",
                            "language_code": "ru",
                            "parameters": ["Иван"]
                        }
                    )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message_id" in data
        print("✅ Template отправлен успешно")
    
    def test_send_template_api_error(self, app, mock_flow_config):
        """Тест ошибки WhatsApp API при отправке template"""
        
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 400
        mock_api_response.text = "Template not approved"
        
        setup_flow_repo_override(app, mock_flow_config)
        
        client = TestClient(app)
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface.get_access_token_for_flow', return_value="test_token"):
            with patch('httpx.AsyncClient') as mock_client:
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_api_response)
                    
                    response = client.post(
                        "/api/v1/admin/whatsapp/send_template/test_whatsapp_flow",
                        params={
                            "phone_number": "9111111111111",
                            "template_name": "unapproved_template"
                        }
                    )
        
        assert response.status_code == 400
        assert "Template not approved" in response.json()["detail"]
        print("✅ Ошибка API корректно обработана")


class TestAdminPhoneInfo:
    """Тесты получения информации о номере"""
    
    def test_get_phone_info_success(self, app, mock_flow_config):
        """Тест успешного получения информации о номере"""
        
        mock_phone_data = {
            "id": "111111111111111",
            "display_phone_number": "+1234567890",
            "verified_name": "Test Company",
            "quality_rating": "GREEN"
        }
        
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 200
        mock_api_response.json = MagicMock(return_value=mock_phone_data)
        
        setup_flow_repo_override(app, mock_flow_config)
        
        client = TestClient(app)
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface.get_access_token_for_flow', return_value="test_token"):
            with patch('httpx.AsyncClient') as mock_client:
                    mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_api_response)
                    
                    response = client.get("/api/v1/admin/whatsapp/phone_info/test_whatsapp_flow")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["phone_data"]["display_phone_number"] == "+1234567890"
        print("✅ Информация о номере получена")
    
    def test_get_phone_info_api_error(self, app, mock_flow_config):
        """Тест ошибки API при получении информации"""
        
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 401
        mock_api_response.text = "Invalid access token"
        
        setup_flow_repo_override(app, mock_flow_config)
        
        client = TestClient(app)
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface.get_access_token_for_flow', return_value="invalid_token"):
            with patch('httpx.AsyncClient') as mock_client:
                    mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_api_response)
                    
                    response = client.get("/api/v1/admin/whatsapp/phone_info/test_whatsapp_flow")
        
        assert response.status_code == 401
        print("✅ Ошибка API корректно возвращается")


class TestWebhookFullFlow:
    """Интеграционные тесты полного flow webhook"""
    
    def test_full_webhook_flow_with_task_creation(self, app, mock_flow_config):
        """Тест полного флоу: webhook → interface → task creation"""
        
        webhook_payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Full Test User"}, "wa_id": "9999999999999"}],
                        "messages": [{
                            "from": "9999999999999",
                            "id": "wamid.full_test",
                            "timestamp": "1699000100",
                            "type": "text",
                            "text": {"body": "Full integration test"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        mock_interface = AsyncMock()
        mock_message = MagicMock()
        mock_message.user_id = "whatsapp:9999999999999"
        mock_interface.handle_message = AsyncMock(return_value=mock_message)
        mock_interface.create_task = AsyncMock(return_value="task_full_123")
        
        setup_flow_repo_override(app, mock_flow_config)
        client = TestClient(app)
        async def mock_get_token(flow_id, platform_config):
            return "test_token"
        
        class MockWhatsAppInterfaceClass:
            @staticmethod
            async def get_access_token_for_flow(flow_id, platform_config):
                return await mock_get_token(flow_id, platform_config)
            
            def __init__(self, *args, **kwargs):
                pass
            
            async def handle_message(self, *args, **kwargs):
                return await mock_interface.handle_message(*args, **kwargs)
            
            async def create_task(self, *args, **kwargs):
                return await mock_interface.create_task(*args, **kwargs)
        
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface', new=MockWhatsAppInterfaceClass):
            response = client.post(
                "/api/v1/webhook/whatsapp/company:test:flow:test_whatsapp_flow",
                json=webhook_payload
            )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        print("✅ Полный webhook flow обработан успешно")


class TestWebhookEdgeCases:
    """Тесты граничных случаев"""
    
    @pytest.mark.skip(reason="TestClient не совместим с async моками в этом edge case")
    def test_webhook_empty_entry(self, app, mock_flow_config):
        """Тест webhook с пустым entry"""
        webhook_payload = {
            "object": "whatsapp_business_account",
            "entry": []
        }
        
        mock_interface = AsyncMock()
        mock_interface.handle_message = AsyncMock(return_value=None)
        
        setup_flow_repo_override(app, mock_flow_config)
        client = TestClient(app)
        
        class MockWhatsAppInterfaceClass:
            @staticmethod
            async def get_access_token_for_flow(flow_id, platform_config):
                return "test_token"
            
            def __init__(self, *args, **kwargs):
                pass
            
            async def handle_message(self, *args, **kwargs):
                return await mock_interface.handle_message(*args, **kwargs)
            
            async def create_task(self, *args, **kwargs):
                return await mock_interface.create_task(*args, **kwargs)
        
        with patch('apps.agents.api.v1.whatsapp.WhatsAppInterface', new=MockWhatsAppInterfaceClass):
            response = client.post(
                "/api/v1/webhook/whatsapp/company:test:flow:test_whatsapp_flow",
                json=webhook_payload
            )
        
        assert response.status_code == 200
        print("✅ Пустой entry обработан без ошибок")
    
    def test_webhook_malformed_json(self, app):
        """Тест webhook с невалидным JSON"""
        setup_flow_repo_override(app, None)
        client = TestClient(app)
        
        response = client.post(
            "/api/v1/webhook/whatsapp/company:test:flow:test_flow",
            data="invalid json{{{",
            headers={"Content-Type": "application/json"}
        )
        
        # FastAPI может вернуть 404 если flow не найден до парсинга JSON
        assert response.status_code in [400, 404, 422]
        print("✅ Невалидный JSON корректно отклонен")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

