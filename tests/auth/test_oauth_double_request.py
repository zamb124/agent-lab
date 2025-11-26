"""
Тест для проверки обработки повторных OAuth запросов.
Проверяет, что код не падает при race condition и двойном использовании кода.
"""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone
from core.models import AuthProvider, AuthRequest, ProviderUserInfo, AuthSession


@pytest.mark.asyncio
async def test_double_oauth_request_with_cache(auth_service, mock_storage_cache, test_user):
    """Второй запрос с тем же кодом должен вернуть кешированный результат"""
    
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
    
    auth_service._storage.get = mock_storage_cache['get']
    auth_service._storage.set = mock_storage_cache['set']
    auth_service._storage.delete = mock_storage_cache['delete']
    
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
    
    request1 = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="test_code_123",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result1 = await auth_service.complete_auth(request1)
    
    assert result1.success is True
    assert result1.user.user_id == test_user.user_id
    assert result1.session.session_id == "session_123"
    assert mock_provider.exchange_code_for_token.call_count == 1
    
    request2 = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="test_code_123",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result2 = await auth_service.complete_auth(request2)
    
    assert result2.success is True
    assert result2.user.user_id == test_user.user_id
    assert result2.session.session_id == "session_123"
    assert mock_provider.exchange_code_for_token.call_count == 1


@pytest.mark.asyncio
async def test_expired_code_with_cache(auth_service, mock_storage_cache, test_user):
    """Если провайдер вернул ошибку "код истек", но есть кеш - вернуть из кеша"""
    
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_token = AsyncMock(
        side_effect=ValueError("Yandex вернул ошибку: 400")
    )
    
    auth_service._providers = {AuthProvider.YANDEX: mock_provider}
    
    test_session = AuthSession(
        session_id="session_123",
        user_id=test_user.user_id,
        provider=AuthProvider.YANDEX,
        access_token="access_token_123",
        refresh_token="refresh_token_123",
        expires_at=datetime.now(timezone.utc).isoformat()
    )
    
    mock_storage_cache['cache']["oauth_code:yandex:expired_code_123"] = f'{{"user_id": "{test_user.user_id}", "session_id": "session_123"}}'
    
    auth_service._storage.get = mock_storage_cache['get']
    auth_service._get_auth_state = AsyncMock(return_value={
        "provider": "yandex",
        "redirect_uri": "http://localhost/callback"
    })
    auth_service._get_user = AsyncMock(return_value=test_user)
    auth_service._get_session = AsyncMock(return_value=test_session)
    
    request = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="expired_code_123",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result = await auth_service.complete_auth(request)
    
    assert result.success is True
    assert result.user.user_id == test_user.user_id
    assert result.session.session_id == "session_123"


@pytest.mark.asyncio
async def test_expired_code_without_cache(auth_service, mock_storage_cache):
    """Если провайдер вернул ошибку "код истек" и нет кеша - вернуть ошибку"""
    
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_token = AsyncMock(
        side_effect=ValueError("Yandex вернул ошибку: 400")
    )
    
    auth_service._providers = {AuthProvider.YANDEX: mock_provider}
    
    auth_service._storage.get = mock_storage_cache['get']
    auth_service._get_auth_state = AsyncMock(return_value={
        "provider": "yandex",
        "redirect_uri": "http://localhost/callback"
    })
    
    request = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="expired_code_456",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result = await auth_service.complete_auth(request)
    
    assert result.success is False
    assert "Yandex вернул ошибку: 400" in result.error_message

