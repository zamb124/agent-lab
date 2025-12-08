"""
Тест для проверки обработки повторных OAuth запросов.
Проверяет, что код не падает при race condition и двойном использовании кода.
"""

import pytest
import json
from unittest.mock import AsyncMock
from datetime import datetime, timezone
from core.models import AuthProvider, AuthRequest, ProviderUserInfo, AuthSession


@pytest.mark.asyncio
async def test_double_oauth_request_with_cache(auth_service, test_user, test_company):
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
    
    test_session = AuthSession(
        session_id="session_123",
        user_id=test_user.user_id,
        provider=AuthProvider.YANDEX,
        access_token="access_token_123",
        refresh_token="refresh_token_123",
        expires_at=datetime.now(timezone.utc).isoformat()
    )
    
    await auth_service.auth_session_repository.set(test_session)
    
    auth_service._get_or_create_user = AsyncMock(return_value=test_user)
    auth_service._create_session = AsyncMock(return_value=test_session)
    auth_service._get_auth_state = AsyncMock(return_value={
        "provider": "yandex",
        "redirect_uri": "http://localhost/callback"
    })
    auth_service._cleanup_auth_state = AsyncMock()
    auth_service._get_user = AsyncMock(return_value=test_user)
    auth_service._get_session = AsyncMock(return_value=test_session)
    
    cached_code_key = f"oauth_code:{AuthProvider.YANDEX.value}:test_code_123"
    await auth_service._storage.delete(cached_code_key)
    
    request1 = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="test_code_123",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result1 = await auth_service.complete_auth(request1)
    
    assert result1.success is True, f"Ожидался успех, но получено: {result1.error_message if result1.error_message else 'unknown error'}"
    assert result1.user.user_id == test_user.user_id
    assert result1.session.session_id == "session_123"
    assert mock_provider.exchange_code_for_token.call_count == 1
    
    cached_code_key = f"oauth_code:{AuthProvider.YANDEX.value}:test_code_123"
    cached_data = await auth_service._storage.get(cached_code_key)
    assert cached_data is not None
    
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
async def test_expired_code_with_cache(auth_service, test_user):
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
    
    await auth_service.auth_session_repository.set(test_session)
    
    cached_code_key = "oauth_code:yandex:expired_code_123"
    cached_data = json.dumps({
        "user_id": test_user.user_id,
        "session_id": "session_123"
    })
    await auth_service._storage.set(cached_code_key, cached_data)
    
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
async def test_expired_code_without_cache(auth_service):
    """Если провайдер вернул ошибку "код истек" и нет кеша - вернуть ошибку"""
    
    mock_provider = AsyncMock()
    mock_provider.exchange_code_for_token = AsyncMock(
        side_effect=ValueError("Yandex вернул ошибку: 400")
    )
    
    auth_service._providers = {AuthProvider.YANDEX: mock_provider}
    
    auth_service._get_auth_state = AsyncMock(return_value={
        "provider": "yandex",
        "redirect_uri": "http://localhost/callback"
    })
    
    cached_code_key = "oauth_code:yandex:expired_code_456"
    cached_data = await auth_service._storage.get(cached_code_key)
    assert cached_data is None
    
    request = AuthRequest(
        provider=AuthProvider.YANDEX,
        code="expired_code_456",
        state="test_state",
        redirect_uri="http://localhost/callback"
    )
    
    result = await auth_service.complete_auth(request)
    
    assert result.success is False
    assert "Yandex вернул ошибку: 400" in result.error_message

