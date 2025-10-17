"""
API для работы с кодом: валидация, форматирование, автокомплит
"""

import ast
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/code", tags=["code"])


class ValidatePythonRequest(BaseModel):
    """Запрос на валидацию Python кода"""
    code: str


class ValidatePythonResponse(BaseModel):
    """Ответ валидации Python кода"""
    valid: bool
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []


@router.post("/validate-python", response_model=ValidatePythonResponse)
async def validate_python_code(request: ValidatePythonRequest) -> ValidatePythonResponse:
    """
    Валидирует Python код без выполнения.
    Проверяет синтаксис через ast.parse и compile.
    """
    code = request.code.strip()
    
    if not code:
        return ValidatePythonResponse(
            valid=False,
            errors=[{"line": 0, "message": "Код пуст", "text": ""}]
        )
    
    try:
        ast.parse(code)
        
        compile(code, '<string>', 'exec')
        
        logger.debug(f"✅ Код валиден ({len(code)} символов)")
        
        return ValidatePythonResponse(
            valid=True,
            errors=[],
            warnings=[]
        )
        
    except SyntaxError as e:
        logger.debug(f"❌ Синтаксическая ошибка: {e.msg} на строке {e.lineno}")
        
        return ValidatePythonResponse(
            valid=False,
            errors=[{
                "line": e.lineno or 0,
                "column": e.offset or 0,
                "message": e.msg or "Синтаксическая ошибка",
                "text": e.text or ""
            }]
        )
    
    except Exception as e:
        logger.error(f"Ошибка валидации кода: {e}", exc_info=True)
        
        return ValidatePythonResponse(
            valid=False,
            errors=[{
                "line": 0,
                "message": f"Ошибка валидации: {str(e)}",
                "text": ""
            }]
        )


class FormatPythonRequest(BaseModel):
    """Запрос на форматирование Python кода"""
    code: str
    line_length: int = 88


class FormatPythonResponse(BaseModel):
    """Ответ форматирования Python кода"""
    formatted: str
    changed: bool
    error: Optional[str] = None


@router.post("/format-python", response_model=FormatPythonResponse)
async def format_python_code(request: FormatPythonRequest) -> FormatPythonResponse:
    """
    Форматирует Python код (в будущем через black или autopep8).
    Пока возвращает исходный код без изменений.
    """
    code = request.code
    
    logger.debug("Форматирование кода (заглушка)")
    
    return FormatPythonResponse(
        formatted=code,
        changed=False,
        error="Форматирование в разработке"
    )


class CompletionRequest(BaseModel):
    """Запрос автокомплита"""
    code: str
    cursor_position: int
    context: Dict[str, Any] = {}


class CompletionItem(BaseModel):
    """Элемент автокомплита"""
    label: str
    value: str
    type: str
    info: Optional[str] = None


class CompletionResponse(BaseModel):
    """Ответ автокомплита"""
    items: List[CompletionItem]


@router.post("/completion", response_model=CompletionResponse)
async def get_code_completion(request: CompletionRequest) -> CompletionResponse:
    """
    Возвращает варианты автокомплита для Python кода.
    В будущем можно интегрировать с Jedi или другими инструментами.
    """
    items = []
    
    standard_libs = [
        {"label": "httpx", "value": "httpx", "type": "module", "info": "Асинхронный HTTP клиент"},
        {"label": "asyncio", "value": "asyncio", "type": "module", "info": "Асинхронное программирование"},
        {"label": "typing", "value": "typing", "type": "module", "info": "Типизация Python"},
        {"label": "json", "value": "json", "type": "module", "info": "Работа с JSON"}
    ]
    
    items.extend([CompletionItem(**item) for item in standard_libs])
    
    return CompletionResponse(items=items)

