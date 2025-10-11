"""
Тест для проверки обработки повторных OAuth запросов.
Проверяет, что код не падает при race condition и двойном использовании кода.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.identity.auth_service import AuthService
from app.identity.models import AuthProvider, AuthRequest, AuthResult, ProviderUserInfo, User, AuthSession


@pytest.mark.asyncio
async def test_double_oauth_request_with_cache():
    """
    Тест: второй запрос с тем же кодом должен вернуть кешированный результат
    """
    auth_service = AuthService()
    
    # Мокаем провайдер
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_token = AsyncMock(return_value=("access_token_123", "refresh_token_123"))
    mock_provider.get_user_info = AsyncMock(return_value=ProviderUserInfo(
        provider_user_id="test_user_123",
        email="test@example.com",
        name="Test User",
        avatar_url=None,
        raw_data={}
    ))
    
    auth_service._providers = {AuthProvider.YANDEX: mock_provider}
    
    # Мокаем storage
    cache = {}
    
    async def mock_get(key, force_global=False):
        return cache.get(key)
    
    async def mock_set(key, value, ttl=None, force_global=False):
        cache[key] = value
        return True
    
    async def mock_delete(key, force_global=False):
        cache.pop(key, None)
        return True
    
    auth_service.storage.get = mock_get
    auth_service.storage.set = mock_set
    auth_service.storage.delete = mock_delete
    
    # Создаем реальные модели
    test_user = User(
        user_id="user_123",
        name="Test User",
        companies={},
        active_company_id=""
    )
    
    test_session = AuthSession(
        session_id="session_123",
        user_id="user_123",
        provider=AuthProvider.YANDEX,
        access_token="access_token_123",
        refresh_token="refresh_token_123",
        expires_at=datetime.now(timezone.utc).isoformat()
    )
    
    auth_service._get_or_create_user = AsyncMock(return_value=test_user)
    auth_service._create_session = AsyncMock(return_value=test_session)
    auth_service._get_auth_state = AsyncMock(return_value={
        "provider": "yandex",
        "redirect_uri": "http://localhost/callback"
    })
    auth_service._cleanup_auth_state = AsyncMock()
    auth_service._get_user = AsyncMock(return_value=test_user)
    auth_service._get_session = AsyncMock(return_value=test_session)
    
    # Первый запрос - должен успешно обменять код
    request1 = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="test_code_123",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result1 = await auth_service.complete_auth(request1)
    
    assert result1.success is True
    assert result1.user.user_id == "user_123"
    assert result1.session.session_id == "session_123"
    assert mock_provider.exchange_code_for_token.call_count == 1
    
    # Второй запрос с тем же кодом - должен вернуть кешированный результат
    request2 = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="test_code_123",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result2 = await auth_service.complete_auth(request2)
    
    assert result2.success is True
    assert result2.user.user_id == "user_123"
    assert result2.session.session_id == "session_123"
    # Провайдер НЕ должен вызываться второй раз
    assert mock_provider.exchange_code_for_token.call_count == 1
    
    print("✅ Тест успешно пройден: второй запрос вернул кешированный результат")


@pytest.mark.asyncio
async def test_expired_code_with_cache():
    """
    Тест: если провайдер вернул ошибку "код истек", но есть кеш - вернуть из кеша
    """
    auth_service = AuthService()
    
    # Мокаем провайдер, который вернет ошибку
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_token = AsyncMock(
        side_effect=ValueError("Yandex вернул ошибку: 400")
    )
    
    auth_service._providers = {AuthProvider.YANDEX: mock_provider}
    
    # Создаем реальные модели
    test_user = User(
        user_id="user_123",
        name="Test User",
        companies={},
        active_company_id=""
    )
    
    test_session = AuthSession(
        session_id="session_123",
        user_id="user_123",
        provider=AuthProvider.YANDEX,
        access_token="access_token_123",
        refresh_token="refresh_token_123",
        expires_at=datetime.now(timezone.utc).isoformat()
    )
    
    # Мокаем storage с готовым кешем
    cache = {
        "oauth_code:yandex:expired_code_123": '{"user_id": "user_123", "session_id": "session_123"}'
    }
    
    async def mock_get(key, force_global=False):
        return cache.get(key)
    
    auth_service.storage.get = mock_get
    auth_service._get_auth_state = AsyncMock(return_value={
        "provider": "yandex",
        "redirect_uri": "http://localhost/callback"
    })
    auth_service._get_user = AsyncMock(return_value=test_user)
    auth_service._get_session = AsyncMock(return_value=test_session)
    
    # Запрос с истекшим кодом
    request = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="expired_code_123",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result = await auth_service.complete_auth(request)
    
    # Должен вернуть успех из кеша, несмотря на ошибку от провайдера
    assert result.success is True
    assert result.user.user_id == "user_123"
    assert result.session.session_id == "session_123"
    
    print("✅ Тест успешно пройден: при ошибке 'код истек' вернулся кешированный результат")


@pytest.mark.asyncio
async def test_expired_code_without_cache():
    """
    Тест: если провайдер вернул ошибку "код истек" и нет кеша - вернуть ошибку
    """
    auth_service = AuthService()
    
    # Мокаем провайдер, который вернет ошибку
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_token = AsyncMock(
        side_effect=ValueError("Yandex вернул ошибку: 400")
    )
    
    auth_service._providers = {AuthProvider.YANDEX: mock_provider}
    
    # Мокаем storage БЕЗ кеша
    cache = {}
    
    async def mock_get(key, force_global=False):
        return cache.get(key)
    
    auth_service.storage.get = mock_get
    auth_service._get_auth_state = AsyncMock(return_value={
        "provider": "yandex",
        "redirect_uri": "http://localhost/callback"
    })
    
    # Запрос с истекшим кодом
    request = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="expired_code_456",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result = await auth_service.complete_auth(request)
    
    # Должен вернуть ошибку, т.к. кеша нет
    assert result.success is False
    assert "Yandex вернул ошибку: 400" in result.error_message
    
    print("✅ Тест успешно пройден: без кеша вернулась ошибка")


if __name__ == "__main__":
    import asyncio
    
    print("🧪 Запуск тестов OAuth двойного запроса...\n")
    
    asyncio.run(test_double_oauth_request_with_cache())
    asyncio.run(test_expired_code_with_cache())
    asyncio.run(test_expired_code_without_cache())
    
    print("\n✅ Все тесты успешно пройдены!")

