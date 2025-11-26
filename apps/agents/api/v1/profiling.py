"""
API для профилирования
"""

import logging
from typing import Dict
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/profiling", tags=["profiling"])


class ProfilingRequest(BaseModel):
    """Запрос на профилирование"""
    url: str
    headers: Dict[str, str] = {}


class ProfilingResponse(BaseModel):
    """Результат профилирования"""
    url: str
    process_time_ms: float
    profile_data: str


@router.get("/health")
async def profiling_health():
    """Проверка работоспособности профилирования"""
    return {
        "status": "ok",
        "message": "Профилирование доступно. Добавьте заголовок X-Enable-Profiling: true к любому запросу"
    }


@router.get("/tips")
async def profiling_tips():
    """Советы по профилированию"""
    return {
        "tips": [
            "Добавьте заголовок 'X-Enable-Profiling: true' к любому запросу для детального профилирования",
            "Результат профилирования будет в заголовке X-Profile-Data (первые 4KB)",
            "Время обработки всегда доступно в заголовке X-Process-Time",
            "Медленные запросы (>500ms) автоматически логируются с ⚠️",
            "Все frontend запросы логируются с временем и иконкой 📊",
            "",
            "Пример curl:",
            "curl -H 'X-Enable-Profiling: true' -H 'Cookie: session_id=...' http://localhost:8001/frontend/dashboard/",
            "",
            "Для браузера установите расширение ModHeader и добавьте заголовок:",
            "X-Enable-Profiling: true",
            "",
            "Смотрите заголовки в DevTools -> Network -> Response Headers"
        ]
    }

