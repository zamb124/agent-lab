"""
Тесты для API endpoints интернационализации
"""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.frontend.api.i18n import router
from app.models.i18n_models import Language, TranslationStats, TranslationFile
from app.models.context_models import Context
from app.identity.models import User, Company, AuthProvider, UserStatus


# Создаем тестовое приложение
from fastapi import FastAPI
test_app = FastAPI()
test_app.include_router(router, prefix="/api/i18n")

client = TestClient(test_app)


class TestTranslationsEndpoint:
    """Тесты для endpoint получения переводов"""
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_get_translations_success(self, mock_get_manager):
        """Проверяем успешное получение переводов"""
        # Мокаем менеджер переводов
        mock_manager = Mock()
        mock_manager.get_translations.return_value = {
            "common.save": "Save",
            "common.cancel": "Cancel",
            "dashboard.title": "Dashboard"
        }
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/api/i18n/translations/en")
        
        assert response.status_code == 200
        data = response.json()
        assert data["common.save"] == "Save"
        assert data["dashboard.title"] == "Dashboard"
        assert len(data) == 3
        
        # Проверяем что менеджер был вызван с правильным языком
        mock_manager.get_translations.assert_called_once_with(Language.EN)
    
    def test_get_translations_invalid_language(self):
        """Проверяем обработку неподдерживаемого языка"""
        response = client.get("/api/i18n/translations/invalid")
        
        assert response.status_code == 500
        assert "Ошибка получения переводов" in response.json()["detail"]
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_get_translations_empty(self, mock_get_manager):
        """Проверяем получение пустых переводов"""
        mock_manager = Mock()
        mock_manager.get_translations.return_value = {}
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/api/i18n/translations/es")
        
        assert response.status_code == 200
        assert response.json() == {}
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_get_translations_manager_exception(self, mock_get_manager):
        """Проверяем обработку исключений в менеджере"""
        mock_get_manager.side_effect = Exception("Manager error")
        
        response = client.get("/api/i18n/translations/ru")
        
        assert response.status_code == 500
        assert "Ошибка получения переводов" in response.json()["detail"]


class TestUserLanguageEndpoint:
    """Тесты для endpoint установки языка пользователя"""
    
    @patch('app.frontend.api.i18n.get_context')
    def test_set_user_language_success(self, mock_get_context):
        """Проверяем успешную установку языка"""
        # Мокаем контекст с пользователем
        mock_user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        mock_context = Context(
            user=mock_user,
            platform="api",
            active_company=None,
            user_companies=[]
        )
        mock_get_context.return_value = mock_context
        
        response = client.post("/api/i18n/user-language", json={"language": "en"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["language"] == "en"
        
        # Проверяем что cookie установлен
        assert "language=en" in response.headers.get("set-cookie", "")
    
    def test_set_user_language_invalid_language(self):
        """Проверяем обработку неподдерживаемого языка"""
        response = client.post("/api/i18n/user-language", json={"language": "invalid"})
        
        assert response.status_code == 400
        assert "Неподдерживаемый язык" in response.json()["detail"]
    
    @patch('app.frontend.api.i18n.get_context')
    def test_set_user_language_no_user(self, mock_get_context):
        """Проверяем обработку запроса без авторизации"""
        mock_get_context.return_value = None
        
        response = client.post("/api/i18n/user-language", json={"language": "en"})
        
        assert response.status_code == 401
        assert "Пользователь не авторизован" in response.json()["detail"]
    
    @patch('app.frontend.api.i18n.get_context')
    def test_set_user_language_empty_data(self, mock_get_context):
        """Проверяем обработку пустых данных"""
        mock_user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        mock_context = Context(
            user=mock_user,
            platform="api",
            active_company=None,
            user_companies=[]
        )
        mock_get_context.return_value = mock_context
        
        response = client.post("/api/i18n/user-language", json={})
        
        assert response.status_code == 400
        assert "Неподдерживаемый язык" in response.json()["detail"]


class TestStatsEndpoint:
    """Тесты для endpoint статистики переводов"""
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_get_stats_success(self, mock_get_manager):
        """Проверяем успешное получение статистики"""
        # Подготавливаем тестовую статистику
        test_stats = TranslationStats(
            total_languages=3,
            total_keys=100,
            languages_stats={
                Language.RU: TranslationFile(
                    language=Language.RU,
                    total_keys=100,
                    translated_keys=100
                ),
                Language.EN: TranslationFile(
                    language=Language.EN,
                    total_keys=100,
                    translated_keys=75
                ),
                Language.ES: TranslationFile(
                    language=Language.ES,
                    total_keys=100,
                    translated_keys=50
                )
            }
        )
        
        mock_manager = Mock()
        mock_manager.get_stats.return_value = test_stats
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/api/i18n/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total_languages"] == 3
        assert data["total_keys"] == 100
        assert len(data["languages_stats"]) == 3
        
        # Проверяем статистику по языкам
        ru_stats = data["languages_stats"]["ru"]
        assert ru_stats["total_keys"] == 100
        assert ru_stats["translated_keys"] == 100
        
        en_stats = data["languages_stats"]["en"]
        assert en_stats["total_keys"] == 100
        assert en_stats["translated_keys"] == 75
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_get_stats_manager_exception(self, mock_get_manager):
        """Проверяем обработку исключений при получении статистики"""
        mock_get_manager.side_effect = Exception("Stats error")
        
        response = client.get("/api/i18n/stats")
        
        assert response.status_code == 500
        assert "Ошибка получения статистики" in response.json()["detail"]


class TestRefreshEndpoint:
    """Тесты для endpoint обновления переводов"""
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    @patch('app.frontend.api.i18n.get_context')
    def test_refresh_translations_success(self, mock_get_context, mock_get_manager):
        """Проверяем успешное обновление переводов"""
        # Мокаем контекст администратора
        mock_user = User(
            user_id="admin_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="admin@example.com",
            name="Admin User",
            status=UserStatus.ACTIVE,
            groups=["admin"],
            companies={"test_company": ["admin"]}
        )
        
        mock_company = Company(
            company_id="test_company",
            name="Test Company",
            subdomain="test",
            status="active"
        )
        
        mock_context = Context(
            user=mock_user,
            platform="api",
            active_company=mock_company,
            user_companies=[mock_company]
        )
        mock_get_context.return_value = mock_context
        
        # Мокаем менеджер переводов
        mock_manager = Mock()
        mock_manager._auto_generate_translations = AsyncMock()
        mock_get_manager.return_value = mock_manager
        
        response = client.post("/api/i18n/refresh")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "обновлены" in data["message"]
    
    @patch('app.frontend.api.i18n.get_context')
    def test_refresh_translations_no_auth(self, mock_get_context):
        """Проверяем отказ в доступе без авторизации"""
        mock_get_context.return_value = None
        
        response = client.post("/api/i18n/refresh")
        
        assert response.status_code == 401
        assert "Пользователь не авторизован" in response.json()["detail"]
    
    @patch('app.frontend.api.i18n.get_context')
    def test_refresh_translations_no_admin_rights(self, mock_get_context):
        """Проверяем отказ в доступе для обычного пользователя"""
        # Мокаем контекст обычного пользователя
        mock_user = User(
            user_id="regular_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="user@example.com",
            name="Regular User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={"test_company": ["user"]}  # Не админ
        )
        
        mock_company = Company(
            company_id="test_company",
            name="Test Company",
            subdomain="test",
            status="active"
        )
        
        mock_context = Context(
            user=mock_user,
            platform="api",
            active_company=mock_company,
            user_companies=[mock_company]
        )
        mock_get_context.return_value = mock_context
        
        response = client.post("/api/i18n/refresh")
        
        assert response.status_code == 403
        assert "Недостаточно прав доступа" in response.json()["detail"]


class TestSupportedLanguagesEndpoint:
    """Тесты для endpoint списка поддерживаемых языков"""
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_get_supported_languages_success(self, mock_get_manager):
        """Проверяем получение списка поддерживаемых языков"""
        mock_manager = Mock()
        mock_manager.get_translations.return_value = {
            "languages.ru": "Русский",
            "languages.en": "English",
            "languages.es": "Español"
        }
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/api/i18n/supported-languages")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ru"] == "Русский"
        assert data["en"] == "English"
        assert data["es"] == "Español"
        assert len(data) == 3
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_get_supported_languages_fallback(self, mock_get_manager):
        """Проверяем fallback при отсутствии переводов названий языков"""
        mock_manager = Mock()
        mock_manager.get_translations.return_value = {}  # Пустые переводы
        mock_get_manager.return_value = mock_manager
        
        response = client.get("/api/i18n/supported-languages")
        
        assert response.status_code == 200
        data = response.json()
        # Должны вернуться коды языков в верхнем регистре как fallback
        assert data["ru"] == "RU"
        assert data["en"] == "EN"
        assert data["es"] == "ES"


class TestCurrentLanguageEndpoint:
    """Тесты для endpoint получения текущего языка"""
    
    @patch('app.frontend.api.i18n.get_context')
    def test_get_current_language_from_context(self, mock_get_context):
        """Проверяем получение языка из контекста"""
        mock_user = User(
            user_id="test_user",
            provider=AuthProvider.YANDEX,
            provider_user_id="123",
            email="test@example.com",
            name="Test User",
            status=UserStatus.ACTIVE,
            groups=["user"],
            companies={}
        )
        
        mock_context = Context(
            user=mock_user,
            platform="api",
            active_company=None,
            user_companies=[],
            language=Language.EN
        )
        mock_get_context.return_value = mock_context
        
        response = client.get("/api/i18n/current-language")
        
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"
        assert data["name"] == "EN"
    
    @patch('app.frontend.api.i18n.get_context')
    def test_get_current_language_no_context(self, mock_get_context):
        """Проверяем fallback при отсутствии контекста"""
        mock_get_context.return_value = None
        
        response = client.get("/api/i18n/current-language")
        
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "ru"  # Fallback на RU
        assert data["name"] == "RU"


class TestTranslateEndpoint:
    """Тесты для endpoint перевода конкретного ключа"""
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_translate_key_success(self, mock_get_manager):
        """Проверяем успешный перевод ключа"""
        mock_manager = Mock()
        mock_manager.t.return_value = "Dashboard"
        mock_get_manager.return_value = mock_manager
        
        response = client.post("/api/i18n/translate", json={
            "key": "dashboard.title",
            "language": "en"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "dashboard.title"
        assert data["translation"] == "Dashboard"
        assert data["language"] == "en"
        
        # Проверяем что менеджер был вызван с правильными параметрами
        mock_manager.t.assert_called_once_with("dashboard.title", Language.EN)
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_translate_key_with_params(self, mock_get_manager):
        """Проверяем перевод с параметрами"""
        mock_manager = Mock()
        mock_manager.t.return_value = "Welcome, John!"
        mock_get_manager.return_value = mock_manager
        
        response = client.post("/api/i18n/translate", json={
            "key": "welcome.message",
            "params": {"name": "John"},
            "language": "en"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["translation"] == "Welcome, John!"
        
        # Проверяем что параметры переданы
        mock_manager.t.assert_called_once_with("welcome.message", Language.EN, name="John")
    
    def test_translate_key_missing_key(self):
        """Проверяем ошибку при отсутствии ключа"""
        response = client.post("/api/i18n/translate", json={
            "language": "en"
        })
        
        assert response.status_code == 400
        assert "Ключ перевода обязателен" in response.json()["detail"]
    
    def test_translate_key_invalid_language(self):
        """Проверяем ошибку при неподдерживаемом языке"""
        response = client.post("/api/i18n/translate", json={
            "key": "test.key",
            "language": "invalid"
        })
        
        assert response.status_code == 400
        assert "Неподдерживаемый язык" in response.json()["detail"]
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_translate_key_auto_language(self, mock_get_manager):
        """Проверяем автоматическое определение языка"""
        mock_manager = Mock()
        mock_manager.t.return_value = "Тест"
        mock_get_manager.return_value = mock_manager
        
        response = client.post("/api/i18n/translate", json={
            "key": "test.key"
            # Язык не указан
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "auto"
        
        # Проверяем что вызвано без языка (автоопределение)
        mock_manager.t.assert_called_once_with("test.key", None)
    
    @patch('app.frontend.api.i18n.get_translation_manager')
    def test_translate_key_manager_exception(self, mock_get_manager):
        """Проверяем обработку исключений в менеджере"""
        mock_get_manager.side_effect = Exception("Translation error")
        
        response = client.post("/api/i18n/translate", json={
            "key": "test.key"
        })
        
        assert response.status_code == 500
        assert "Ошибка перевода" in response.json()["detail"]


class TestAPIErrorHandling:
    """Тесты обработки ошибок в API"""
    
    def test_invalid_json(self):
        """Проверяем обработку некорректного JSON"""
        response = client.post("/api/i18n/user-language", 
                             content="invalid json",
                             headers={"content-type": "application/json"})
        
        assert response.status_code == 422
    
    def test_missing_content_type(self):
        """Проверяем обработку отсутствующего Content-Type"""
        response = client.post("/api/i18n/user-language", 
                             data="test data")
        
        assert response.status_code == 422
