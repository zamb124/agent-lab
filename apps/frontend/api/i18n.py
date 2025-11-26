"""
API для работы с системой интернационализации
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.models.i18n_models import Language, TranslationStats
from core.i18n import get_translation_manager
from core.context import get_context

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/translations/{language}")
async def get_translations(language: str) -> Dict[str, str]:
    """
    Получить все переводы для указанного языка
    
    Args:
        language: Код языка (ru, en, es)
        
    Returns:
        Словарь с переводами
    """
    try:
        # Валидируем язык
        try:
            lang_enum = Language(language.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Неподдерживаемый язык: {language}")
        
        # Получаем переводы
        manager = get_translation_manager()
        translations = manager.get_translations(lang_enum)
        
        logger.debug(f"Отправлено {len(translations)} переводов для языка {language}")
        
        return translations
        
    except Exception as e:
        logger.error(f"Ошибка получения переводов для {language}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения переводов")


@router.post("/user-language")
async def set_user_language(request: Request, data: Dict[str, Any]) -> JSONResponse:
    """
    Установить предпочитаемый язык пользователя
    
    Args:
        data: {"language": "ru|en|es"}
        
    Returns:
        Статус операции
    """
    try:
        language = data.get("language", "").lower()
        
        # Валидируем язык
        try:
            Language(language)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Неподдерживаемый язык: {language}")
        
        # Получаем контекст пользователя
        context = get_context()
        if not context or not context.user:
            raise HTTPException(status_code=401, detail="Пользователь не авторизован")
        
        # Здесь можно сохранить язык пользователя в базе данных
        # Пока что просто логируем
        logger.info(f"Пользователь {context.user.user_id} выбрал язык: {language}")
        
        # Устанавливаем cookie для сохранения выбора
        response = JSONResponse(content={"status": "success", "language": language})
        response.set_cookie(
            key="language",
            value=language,
            max_age=365 * 24 * 60 * 60,  # 1 год
            path="/",
            httponly=False,  # Должен быть доступен из JavaScript
            samesite="lax"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка установки языка пользователя: {e}")
        raise HTTPException(status_code=500, detail="Ошибка установки языка")


@router.get("/stats")
async def get_translation_stats() -> TranslationStats:
    """
    Получить статистику переводов
    
    Returns:
        Статистика по всем языкам
    """
    try:
        manager = get_translation_manager()
        stats = manager.get_stats()
        
        logger.debug(f"Отправлена статистика переводов: {stats.total_keys} ключей, {stats.total_languages} языков")
        
        return stats
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики переводов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения статистики")


@router.post("/refresh")
async def refresh_translations() -> JSONResponse:
    """
    Принудительное обновление переводов (перегенерация из кода)
    
    Returns:
        Статус операции
    """
    try:
        # Проверяем права администратора
        context = get_context()
        if not context or not context.user:
            raise HTTPException(status_code=401, detail="Пользователь не авторизован")
        
        # Проверяем является ли пользователь админом
        user_roles = []
        if context.active_company and context.active_company.company_id in context.user.companies:
            user_roles = context.user.companies[context.active_company.company_id]
        
        if "admin" not in user_roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав доступа")
        
        # Выполняем обновление переводов
        manager = get_translation_manager()
        await manager._auto_generate_translations()
        
        logger.info(f"Переводы обновлены администратором: {context.user.user_id}")
        
        return JSONResponse(content={
            "status": "success",
            "message": "Переводы успешно обновлены"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления переводов: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обновления переводов")


@router.get("/supported-languages")
async def get_supported_languages() -> Dict[str, str]:
    """
    Получить список поддерживаемых языков
    
    Returns:
        Словарь {код_языка: название_языка}
    """
    try:
        # Получаем переводы названий языков из русской версии
        manager = get_translation_manager() 
        ru_translations = manager.get_translations(Language.RU)
        
        languages = {}
        for lang in Language:
            # Пытаемся получить переведенное название языка
            lang_key = f"languages.{lang.value}"
            lang_name = ru_translations.get(lang_key, lang.value.upper())
            languages[lang.value] = lang_name
        
        return languages
        
    except Exception as e:
        logger.error(f"Ошибка получения списка языков: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения списка языков")


@router.get("/current-language")
async def get_current_language() -> Dict[str, str]:
    """
    Получить текущий язык пользователя
    
    Returns:
        Информация о текущем языке
    """
    try:
        context = get_context()
        current_lang = context.language if context else Language.RU
        
        return {
            "language": current_lang.value,
            "name": current_lang.value.upper()
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения текущего языка: {e}")
        raise HTTPException(status_code=500, detail="Ошибка получения текущего языка")


@router.post("/translate")
async def translate_key(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Перевести конкретный ключ
    
    Args:
        data: {"key": "translation_key", "params": {}, "language": "ru"}
        
    Returns:
        Переведенное значение
    """
    try:
        key = data.get("key", "")
        params = data.get("params", {})
        language = data.get("language")
        
        if not key:
            raise HTTPException(status_code=400, detail="Ключ перевода обязателен")
        
        # Определяем язык
        lang_enum = None
        if language:
            try:
                lang_enum = Language(language.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Неподдерживаемый язык: {language}")
        
        # Получаем перевод
        manager = get_translation_manager()
        translation = manager.t(key, lang_enum, **params)
        
        return {
            "key": key,
            "translation": translation,
            "language": lang_enum.value if lang_enum else "auto"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка перевода ключа {data.get('key', '')}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка перевода")
