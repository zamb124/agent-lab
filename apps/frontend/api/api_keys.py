"""
API для управления API ключами компании
"""
import logging
import secrets
import hashlib
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException, Request
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import ApiKey, ApiKeyCreate, ApiKeyUpdate, ApiKeyCreated

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


def generate_api_key() -> tuple[str, str]:
    """
    Генерирует API ключ и его хеш
    
    Returns:
        (secret_key, key_hash) - секретный ключ и его хеш для хранения
    """
    secret = f"hum_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(secret.encode()).hexdigest()
    return secret, key_hash


@router.get("", response_model=List[ApiKey])
async def list_api_keys(request: Request, container: ContainerDep):
    """
    Получить список API ключей компании
    
    Returns:
        Список API ключей (без секретов)
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    company = request.state.company
    
    # TODO: Создать ApiKeyRepository для хранения ключей
    # Пока возвращаем mock данные
    mock_keys = []
    
    logger.info(f"Запрошены API ключи для компании {company.company_id}")
    
    return mock_keys


@router.post("", response_model=ApiKeyCreated)
async def create_api_key(
    key_data: ApiKeyCreate,
    request: Request,
    container: ContainerDep
):
    """
    Создать новый API ключ
    
    ВАЖНО: Секрет возвращается только при создании!
    
    Args:
        key_data: Данные ключа (название + scopes)
    
    Returns:
        Созданный ключ с секретом
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []) and \
       'admin' not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    valid_scopes = [
        'agents:read', 'agents:write',
        'crm:read', 'crm:write',
        'rag:read', 'rag:write',
        'billing:read'
    ]
    
    for scope in key_data.scopes:
        if scope not in valid_scopes:
            raise HTTPException(
                status_code=400,
                detail=f"Недопустимый scope: {scope}. Допустимые: {', '.join(valid_scopes)}"
            )
    
    secret, key_hash = generate_api_key()
    key_id = f"key_{secrets.token_urlsafe(16)}"
    
    # TODO: Сохранить в ApiKeyRepository
    # api_key = ApiKey(
    #     key_id=key_id,
    #     name=key_data.name,
    #     key_prefix=secret[:12],
    #     scopes=key_data.scopes,
    #     company_id=company.company_id,
    #     created_by=user.user_id
    # )
    # await api_key_repo.set(api_key)
    
    logger.info(f"Создан API ключ {key_id} для компании {company.company_id}")
    
    return ApiKeyCreated(
        key_id=key_id,
        name=key_data.name,
        secret=secret,
        scopes=key_data.scopes,
        message="Сохраните секрет - он больше не будет показан!"
    )


@router.patch("/{key_id}")
async def update_api_key(
    key_id: str,
    update: ApiKeyUpdate,
    request: Request,
    container: ContainerDep
):
    """
    Обновить название API ключа
    
    Args:
        key_id: ID ключа
        update: Новые данные
    
    Returns:
        Обновленный ключ
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []) and \
       'admin' not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    # TODO: Обновить в ApiKeyRepository
    logger.info(f"Обновлен API ключ {key_id}")
    
    return {
        "success": True,
        "key_id": key_id,
        "name": update.name
    }


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: str,
    request: Request,
    container: ContainerDep
):
    """
    Отозвать API ключ
    
    Args:
        key_id: ID ключа
    
    Returns:
        Результат отзыва
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []) and \
       'admin' not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    # TODO: Удалить из ApiKeyRepository
    logger.info(f"Отозван API ключ {key_id}")
    
    return {
        "success": True,
        "message": "API ключ отозван"
    }


