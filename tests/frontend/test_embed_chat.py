"""
Тесты для встраиваемого чата
"""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.frontend.modules.chat.router import router
from app.core.tokens import get_token_service


class TestEmbedChatEndpoint:
    """Тесты для endpoint встраиваемого чата"""
    
    @pytest.fixture
    def app(self):
        """Фикстура для FastAPI приложения"""
        app = FastAPI()
        app.include_router(router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Фикстура для тестового клиента"""
        return TestClient(app)
    
    @pytest.fixture
    def valid_token(self):
        """Фикстура для валидного токена"""
        token_service = get_token_service()
        return token_service.create_token(
            user_id="test_user_123",
            company_id="test_company_456",
            session_id="test_session_789",
            expires_in=3600,
            metadata={"test": "embed"}
        )
    
    def test_embed_chat_success(self, client, valid_token):
        """Тест успешного встраивания чата"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": valid_token,
                "flow_id": "test_flow_123",
                "session_id": "test_session_456",
                "theme": "dark",
                "width": "500px",
                "height": "700px",
                "user_id": "test_user_789"
            }
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Проверяем, что в ответе есть основные элементы
        content = response.text
        assert "chat-widget" in content or "embed" in content.lower()
    
    def test_embed_chat_minimal_params(self, client, valid_token):
        """Тест встраивания чата с минимальными параметрами"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": valid_token,
                "flow_id": "test_flow_123"
            }
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_embed_chat_invalid_token(self, client):
        """Тест встраивания чата с недействительным токеном"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": "invalid_token_123",
                "flow_id": "test_flow_123"
            }
        )
        
        assert response.status_code == 401
        assert "Недействительный или истекший токен доступа" in response.json()["detail"]
    
    def test_embed_chat_expired_token(self, client):
        """Тест встраивания чата с истекшим токеном"""
        # Создаем токен с очень коротким временем жизни
        token_service = get_token_service()
        expired_token = token_service.create_token(
            user_id="test_user_123",
            expires_in=1  # 1 секунда
        )
        
        import time
        time.sleep(2)  # Ждем истечения токена
        
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": expired_token,
                "flow_id": "test_flow_123"
            }
        )
        
        assert response.status_code == 401
        assert "Недействительный или истекший токен доступа" in response.json()["detail"]
    
    def test_embed_chat_missing_token(self, client):
        """Тест встраивания чата без токена"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "flow_id": "test_flow_123"
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_embed_chat_missing_flow_id(self, client, valid_token):
        """Тест встраивания чата без flow_id"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": valid_token
            }
        )
        
        assert response.status_code == 422  # Validation error
    
    def test_embed_chat_invalid_theme(self, client, valid_token):
        """Тест встраивания чата с недействительной темой"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": valid_token,
                "flow_id": "test_flow_123",
                "theme": "invalid_theme"
            }
        )
        
        # Должен вернуть 200, но с темой по умолчанию (light)
        assert response.status_code == 200
    
    def test_embed_chat_dark_theme(self, client, valid_token):
        """Тест встраивания чата с темной темой"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": valid_token,
                "flow_id": "test_flow_123",
                "theme": "dark"
            }
        )
        
        assert response.status_code == 200
        content = response.text
        assert "dark" in content.lower()
    
    def test_embed_chat_custom_dimensions(self, client, valid_token):
        """Тест встраивания чата с кастомными размерами"""
        response = client.get(
            "/frontend/chat/embed",
            params={
                "token": valid_token,
                "flow_id": "test_flow_123",
                "width": "800px",
                "height": "1000px"
            }
        )
        
        assert response.status_code == 200
        content = response.text
        assert "800px" in content
        assert "1000px" in content


class TestCreateEmbedTokenEndpoint:
    """Тесты для endpoint создания токена встраивания"""
    
    @pytest.fixture
    def app(self):
        """Фикстура для FastAPI приложения"""
        app = FastAPI()
        app.include_router(router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Фикстура для тестового клиента"""
        return TestClient(app)
    
    @pytest.fixture
    def valid_auth_token(self):
        """Фикстура для валидного токена авторизации"""
        token_service = get_token_service()
        return token_service.create_token(
            user_id="test_user_123",
            company_id="test_company_456",
            session_id="test_session_789",
            expires_in=3600
        )
    
    def test_create_embed_token_success(self, client, valid_auth_token):
        """Тест успешного создания токена встраивания"""
        response = client.post(
            "/frontend/chat/create-embed-token",
            params={
                "flow_id": "test_flow_123",
                "expires_in": 7200,
                "user_id": "test_user_456",
                "company_id": "test_company_789"
            },
            cookies={"session_id": valid_auth_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert "flow_id" in data
        assert "expires_in" in data
        assert "embed_url" in data
        
        assert data["flow_id"] == "test_flow_123"
        assert data["expires_in"] == 7200
        assert "embed" in data["embed_url"]
        
        # Проверяем, что созданный токен валиден
        token_service = get_token_service()
        token_data = token_service.validate_token(data["token"])
        assert token_data is not None
        assert token_data.user_id == "test_user_123"  # Используется user_id из токена авторизации
        assert token_data.company_id == "test_company_789"  # Используется company_id из параметров
        assert token_data.metadata["flow_id"] == "test_flow_123"
        assert token_data.metadata["embed"] is True
    
    def test_create_embed_token_minimal_params(self, client, valid_auth_token):
        """Тест создания токена встраивания с минимальными параметрами"""
        response = client.post(
            "/frontend/chat/create-embed-token",
            params={
                "flow_id": "test_flow_123"
            },
            cookies={"session_id": valid_auth_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "token" in data
        assert data["flow_id"] == "test_flow_123"
        assert data["expires_in"] == 86400  # По умолчанию 24 часа
    
    def test_create_embed_token_no_auth(self, client):
        """Тест создания токена встраивания без авторизации"""
        response = client.post(
            "/frontend/chat/create-embed-token",
            params={
                "flow_id": "test_flow_123"
            }
        )
        
        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]
    
    def test_create_embed_token_invalid_auth(self, client):
        """Тест создания токена встраивания с недействительной авторизацией"""
        response = client.post(
            "/frontend/chat/create-embed-token",
            params={
                "flow_id": "test_flow_123"
            },
            cookies={"session_id": "invalid_token"}
        )
        
        assert response.status_code == 401
        assert "Invalid authentication token" in response.json()["detail"]
    
    def test_create_embed_token_missing_flow_id(self, client, valid_auth_token):
        """Тест создания токена встраивания без flow_id"""
        response = client.post(
            "/frontend/chat/create-embed-token",
            cookies={"session_id": valid_auth_token}
        )
        
        assert response.status_code == 422  # Validation error


class TestEmbedChatIntegration:
    """Интеграционные тесты для встраиваемого чата"""
    
    @pytest.fixture
    def app(self):
        """Фикстура для FastAPI приложения"""
        app = FastAPI()
        app.include_router(router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Фикстура для тестового клиента"""
        return TestClient(app)
    
    def test_full_embed_flow(self, client):
        """Тест полного цикла создания токена и встраивания чата"""
        # 1. Создаем токен авторизации
        token_service = get_token_service()
        auth_token = token_service.create_token(
            user_id="integration_user",
            company_id="integration_company",
            session_id="integration_session",
            expires_in=3600
        )
        
        # 2. Создаем токен для встраивания
        response = client.post(
            "/frontend/chat/create-embed-token",
            params={
                "flow_id": "integration_flow",
                "expires_in": 1800,  # 30 минут
                "user_id": "embed_user",
                "company_id": "embed_company"
            },
            cookies={"session_id": auth_token}
        )
        
        assert response.status_code == 200
        embed_data = response.json()
        embed_token = embed_data["token"]
        
        # 3. Используем токен для встраивания чата
        embed_response = client.get(
            "/frontend/chat/embed",
            params={
                "token": embed_token,
                "flow_id": "integration_flow",
                "session_id": "chat_session_123",
                "theme": "dark",
                "width": "600px",
                "height": "800px"
            }
        )
        
        assert embed_response.status_code == 200
        assert "text/html" in embed_response.headers["content-type"]
        
        # 4. Проверяем, что токен содержит правильные метаданные
        token_data = token_service.validate_token(embed_token)
        assert token_data is not None
        assert token_data.user_id == "integration_user"  # Используется user_id из токена авторизации
        assert token_data.company_id == "embed_company"  # Используется company_id из параметров
        assert token_data.metadata["flow_id"] == "integration_flow"
        assert token_data.metadata["embed"] is True
    
    def test_embed_token_with_metadata(self, client):
        """Тест создания токена встраивания с дополнительными метаданными"""
        token_service = get_token_service()
        auth_token = token_service.create_token(
            user_id="metadata_user",
            company_id="metadata_company",
            expires_in=3600
        )
        
        response = client.post(
            "/frontend/chat/create-embed-token",
            params={
                "flow_id": "metadata_flow",
                "expires_in": 3600
            },
            cookies={"session_id": auth_token}
        )
        
        assert response.status_code == 200
        embed_data = response.json()
        
        # Проверяем метаданные токена
        token_data = token_service.validate_token(embed_data["token"])
        assert token_data.metadata["flow_id"] == "metadata_flow"
        assert token_data.metadata["embed"] is True
        assert token_data.metadata["created_by"] == "metadata_user"
    
    def test_multiple_embed_tokens_same_user(self, client):
        """Тест создания нескольких токенов встраивания для одного пользователя"""
        token_service = get_token_service()
        auth_token = token_service.create_token(
            user_id="multi_user",
            company_id="multi_company",
            expires_in=3600
        )
        
        flow_ids = ["flow_1", "flow_2", "flow_3"]
        tokens = []
        
        for flow_id in flow_ids:
            response = client.post(
                "/frontend/chat/create-embed-token",
                params={
                    "flow_id": flow_id,
                    "expires_in": 1800
                },
                cookies={"session_id": auth_token}
            )
            
            assert response.status_code == 200
            embed_data = response.json()
            tokens.append(embed_data["token"])
        
        # Проверяем, что все токены разные
        assert len(set(tokens)) == len(tokens)
        
        # Проверяем, что каждый токен валиден и содержит правильный flow_id
        for i, token in enumerate(tokens):
            token_data = token_service.validate_token(token)
            assert token_data is not None
            assert token_data.metadata["flow_id"] == flow_ids[i]
            assert token_data.metadata["embed"] is True
