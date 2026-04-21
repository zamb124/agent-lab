"""
Middleware для профилирования запросов
"""

import logging
import time
import cProfile
import pstats
import io
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar

logger = logging.getLogger(__name__)

profiling_enabled: ContextVar[bool] = ContextVar("profiling_enabled", default=False)
profiler_output: ContextVar[Optional[str]] = ContextVar("profiler_output", default=None)


class ProfilingMiddleware(BaseHTTPMiddleware):
    """Middleware для профилирования запросов"""

    def __init__(self, app, log_slow_requests: bool = True, slow_threshold_ms: float = 500):
        super().__init__(app)
        self.log_slow_requests = log_slow_requests
        self.slow_threshold_ms = slow_threshold_ms

    async def dispatch(self, request: Request, call_next):
        # Пропускаем статику
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        # Проверяем, нужно ли детальное профилирование
        enable_profiling = request.headers.get("X-Enable-Profiling") == "true"
        
        start_time = time.time()
        
        if enable_profiling:
            # Детальное профилирование через cProfile
            profiler = cProfile.Profile()
            profiler.enable()
            
            response = await call_next(request)
            
            profiler.disable()
            
            # Формируем вывод профилировщика
            output = io.StringIO()
            stats = pstats.Stats(profiler, stream=output)
            stats.sort_stats('cumulative')
            stats.print_stats(50)  # Топ 50 функций
            
            profile_data = output.getvalue()
            
            # Сохраняем в response headers (первые 4KB)
            response.headers["X-Profile-Data"] = profile_data[:4096]
            
            process_time = (time.time() - start_time) * 1000
            response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
            
            logger.info(
                f"ПРОФИЛИРОВАНИЕ: {request.method} {request.url.path} "
                f"[{process_time:.2f}ms]\n{profile_data[:2000]}"
            )
            
            return response
        else:
            # Обычный замер времени
            response = await call_next(request)
            
            process_time = (time.time() - start_time) * 1000
            response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
            
            # Логируем медленные запросы
            if self.log_slow_requests and process_time > self.slow_threshold_ms:
                logger.warning(
                    f"⚠️ МЕДЛЕННЫЙ ЗАПРОС: {request.method} {request.url.path} "
                    f"[{process_time:.2f}ms]"
                )
            elif request.url.path.startswith("/frontend/"):
                # Логируем все frontend запросы с временем
                logger.info(
                    f"📊 {request.method} {request.url.path} [{process_time:.2f}ms]"
                )
            
            return response

