"""
Управление токенами платформ.
Универсальные endpoints для всех платформ.
"""
import logging
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.storage import Storage

logger = logging.getLogger(__name__)

router = APIRouter()


class TokenRequest(BaseModel):
    """Запрос на установку токена"""
    platform: str  # telegram, api, discord, etc.
    username: str  # agents_lab_bot, default, game_bot, etc.
    token: str     # Сам токен


class TokenResponse(BaseModel):
    """Ответ после установки токена"""
    success: bool
    platform: str
    username: str
    token_key: str


@router.post("/admin/tokens", response_model=TokenResponse)
async def set_platform_token(request: TokenRequest):
    """
    Устанавливает токен для платформы и username.
    
    Примеры:
    - platform=telegram, username=agents_lab_bot → token:telegram:agents_lab_bot
    - platform=api, username=default → token:api:default
    """
    try:
        storage = Storage()
        
        # Формируем ключ
        token_key = f"token:{request.platform}:{request.username}"
        
        # Сохраняем токен как JSON
        await storage.set(token_key, json.dumps(request.token))
        
        logger.info(f"✅ Токен установлен: {token_key}")
        
        return TokenResponse(
            success=True,
            platform=request.platform,
            username=request.username,
            token_key=token_key
        )
        
    except Exception as e:
        logger.error(f"Ошибка установки токена: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/tokens/{platform}/{username}")
async def get_platform_token(platform: str, username: str):
    """
    Получает токен для платформы (без самого токена в ответе).
    """
    try:
        storage = Storage()
        token_key = f"token:{platform}:{username}"
        
        token_json = await storage.get(token_key)
        
        if token_json:
            return {
                "exists": True,
                "platform": platform,
                "username": username,
                "token_key": token_key,
                "token_length": len(json.loads(token_json)) if token_json else 0
            }
        else:
            return {
                "exists": False,
                "platform": platform,
                "username": username,
                "token_key": token_key
            }
            
    except Exception as e:
        logger.error(f"Ошибка получения токена: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/tokens/{platform}/{username}")
async def delete_platform_token(platform: str, username: str):
    """
    Удаляет токен для платформы.
    """
    try:
        storage = Storage()
        token_key = f"token:{platform}:{username}"
        
        # Проверяем что токен существует
        token_json = await storage.get(token_key)
        if not token_json:
            raise HTTPException(status_code=404, detail=f"Token {token_key} not found")
        
        # Удаляем токен
        await storage.delete(token_key)
        
        logger.info(f"🗑️ Токен удален: {token_key}")
        
        return {
            "success": True,
            "platform": platform,
            "username": username,
            "token_key": token_key,
            "message": "Token deleted"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка удаления токена: {e}")
        raise HTTPException(status_code=500, detail=str(e))
